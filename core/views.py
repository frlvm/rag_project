from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import StudentRegistrationForm, SubjectCreateForm
from .models import Document, Subject, StudentProfile, TeacherProfile, ChatMessage, TextChunk, User
from django.contrib.auth.views import LoginView
from core.services.rag_pipeline import answer_question
from core.services.document_processor import DocumentTextExtractionError, process_document
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
import logging
from time import perf_counter
from core.services.vector_store import ChromaVectorStore
from django.contrib.auth import authenticate
from core.services.logging_utils import log_document_delete_event, log_event
from core.services.gigachat_client import ask_gigachat
from django.utils import timezone
from pathlib import Path


logger = logging.getLogger("core.rag")
SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx"}


@require_http_methods(["GET"])
def health_check(request):
    """Что делает: сообщает, что Django запущен и обрабатывает HTTP-запросы.
    Входные данные: request — GET-запрос проверки состояния приложения.
    Выходные данные: JSON со статусом ok и HTTP 200.
    """
    return JsonResponse({"status": "ok"})


def _message_time(value):
    """Что делает: форматирует дату сообщения в локальное время.
    Входные данные: value — дата и время сообщения.
    Выходные данные: строка времени в формате «ЧЧ:ММ».
    """
    return timezone.localtime(value).strftime("%H:%M")


def _document_display_name(document):
    """Что делает: получает название документа без расширения файла.
    Входные данные: document — объект Document.
    Выходные данные: строка с названием документа.
    """
    return Path(document.title).stem


def _format_source(source):
    """Что делает: формирует подпись источника с названием документа и страницами.
    Входные данные: source — словарь с данными источника.
    Выходные данные: строка с подписью источника или пустая строка.
    """
    title = source.get("document_title")
    if not title:
        return ""

    page_start = source.get("page_start")
    page_end = source.get("page_end")

    if page_start and page_end and page_start != page_end:
        return f"{title}, стр. {page_start}-{page_end}"
    if page_start:
        return f"{title}, стр. {page_start}"
    return title


def _append_sources_to_answer(answer_text, sources):
    """Что делает: добавляет список источников к тексту ответа.
    Входные данные: answer_text — текст ответа; sources — список источников.
    Выходные данные: строка ответа с источниками или исходный текст.
    """
    formatted_sources = [
        formatted
        for formatted in (_format_source(source) for source in sources or [])
        if formatted
    ]

    if not formatted_sources:
        return answer_text

    sources_text = "\n".join(f"- {source}" for source in formatted_sources)
    return f"{answer_text.rstrip()}\n\nИсточники:\n{sources_text}"


class CustomLoginView(LoginView):
    """Что делает: обрабатывает авторизацию и перенаправление пользователя.
    Входные данные: HTTP-запрос и данные формы, обрабатываемые LoginView.
    Выходные данные: HTTP-ответ с формой входа или перенаправлением.
    """

    template_name = "core/login.html"

    def form_valid(self, form):
        """Что делает: проверяет наличие профиля для роли перед авторизацией.
        Входные данные: form — валидная форма с найденным пользователем.
        Выходные данные: редирект после входа или форма с сообщением об ошибке.
        """
        user = form.get_user()
        profile_exists = (
            user.role == "student"
            and StudentProfile.objects.filter(user=user).exists()
        ) or (
            user.role == "teacher"
            and TeacherProfile.objects.filter(user=user).exists()
        )

        if not profile_exists:
            messages.error(self.request, "Пользователь не найден")
            return super().form_invalid(form)

        return super().form_valid(form)

    def form_invalid(self, form):
        """Что делает: выводит понятную причину ошибки авторизации.
        Входные данные: form — невалидная форма входа.
        Выходные данные: HTTP-ответ с формой и сообщением об ошибке.
        """
        username = self.request.POST.get("username")
        password = self.request.POST.get("password")

        user = User.objects.filter(username=username).first()

        if not user:
            messages.error(self.request, "Пользователь не найден")
        else:
            user_auth = authenticate(
                self.request,
                username=username,
                password=password
            )
            if user_auth is None:
                messages.error(self.request, "Неверный пароль")

        return super().form_invalid(form)

    def get_success_url(self):
        """Что делает: выбирает профиль для перехода после входа согласно роли.
        Входные данные: авторизованный пользователь из self.request.user.
        Выходные данные: строка URL профиля преподавателя или студента.
        """
        user = self.request.user

        if user.role == 'teacher':
            return reverse('teacher_profile')
        return reverse('student_profile')

@login_required
@require_http_methods(["POST"])
def delete_document(request, doc_id):
    """Что делает: удаляет документ, файл и связанные чанки из хранилищ.
    Входные данные: request — HTTP-запрос; doc_id — идентификатор документа.
    Выходные данные: редирект к материалам предмета либо HTTP 403/405.
    """
    started_at = perf_counter()
    document = get_object_or_404(Document, id=doc_id)

    if document.subject.teacher.user != request.user:
        return HttpResponseForbidden("Нет доступа")

    subject_id = document.subject.id
    document_data = {
        "document_id": document.id,
        "document_title": document.title,
        "file_path": document.file.path if document.file else "не указан",
        "file_size": document.file.size if document.file else 0,
        "subject_id": document.subject.id,
        "subject_name": document.subject.name,
        "teacher_name": document.subject.teacher.full_name,
    }

    vector_store = ChromaVectorStore()
    chroma_chunks = vector_store.collection.get(
        where={"document_id": str(document.id)}
    )
    chroma_found_ids = [str(chunk_id) for chunk_id in chroma_chunks.get("ids", [])]

    vector_store.collection.delete(
        where={"document_id": str(document.id)}
    )
    chroma_remaining_chunks = vector_store.collection.get(
        where={"document_id": str(document.id)}
    )
    chroma_remaining_ids = [
        str(chunk_id)
        for chunk_id in chroma_remaining_chunks.get("ids", [])
    ]

    chunks = TextChunk.objects.filter(document=document)
    postgresql_found_ids = [str(chunk_id) for chunk_id in chunks.values_list("id", flat=True)]
    deleted_count, _ = chunks.delete()

    document.file.delete(save=False)
    document.delete()

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    log_document_delete_event(
        document_data=document_data,
        postgresql_found_ids=postgresql_found_ids,
        postgresql_deleted_ids=postgresql_found_ids if deleted_count else [],
        chroma_found_ids=chroma_found_ids,
        chroma_deleted_ids=chroma_found_ids,
        chroma_remaining_ids=chroma_remaining_ids,
        duration_ms=duration_ms,
    )

    messages.success(
        request,
        f"Документ удалён. Чанков: {deleted_count}"
    )

    return redirect("subject_materials", subject_id=subject_id)


@login_required
def subject_materials(request, subject_id):
    """Что делает: показывает материалы предмета и обрабатывает загрузку документов.
    Входные данные: request — GET- или POST-запрос; subject_id — идентификатор предмета.
    Выходные данные: HTML-страница, редирект после загрузки или HTTP 403.
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return HttpResponseForbidden("Доступ только для преподавателей")

    subject = get_object_or_404(
        Subject,
        id=subject_id,
        teacher=teacher
    )

    upload_error = None

    if request.method == "POST":
        file = request.FILES.get("file")

        if file:
            file_extension = Path(file.name).suffix.lower()
            if file_extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
                upload_error = "Неподдерживаемый формат файла. Можно загрузить PDF или Word (.docx)."
            else:
                document = Document.objects.create(
                    title=file.name,
                    file=file,
                    subject=subject
                )

                try:
                    process_document(document)
                except DocumentTextExtractionError as exc:
                    document.file.delete(save=False)
                    document.delete()
                    upload_error = str(exc) or "Не удалось извлечь текст из файла."
                else:
                    return redirect("subject_materials", subject_id=subject.id)

        if not file:
            upload_error = "Выберите файл для загрузки."

    documents = subject.documents.all().order_by("-uploaded_at")

    return render(request, "core/subject_materials.html", {
        "subject": subject,
        "documents": documents,
        "upload_error": upload_error,
    })






@login_required
def index(request):
    """Что делает: перенаправляет пользователя в профиль согласно его роли.
    Входные данные: request — HTTP-запрос авторизованного пользователя.
    Выходные данные: HTTP-редирект в профиль преподавателя или студента.
    """
    if request.user.role == 'teacher':
        return redirect('/teacher/profile/')
    return redirect('/student/profile/')


def student_register(request):
    """Что делает: отображает и обрабатывает регистрацию студента.
    Входные данные: request — GET-запрос или POST-запрос с данными формы.
    Выходные данные: HTML-страница формы или редирект на страницу входа.
    """
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = StudentRegistrationForm()

    return render(request, 'core/student_register.html', {'form': form})


@login_required
def student_profile(request):
    """Что делает: отображает профиль студента и доступные предметы.
    Входные данные: request — HTTP-запрос авторизованного пользователя.
    Выходные данные: HTML-страница профиля студента.
    """
    student = StudentProfile.objects.get(user=request.user)

    return render(request, 'core/student_profile.html', {
        'student': student,
        'subjects': student.subjects.all()
    })


@login_required
def teacher_profile(request):
    """Что делает: отображает профиль преподавателя и его предметы.
    Входные данные: request — HTTP-запрос авторизованного пользователя.
    Выходные данные: HTML-страница профиля преподавателя.
    """
    teacher = TeacherProfile.objects.get(user=request.user)

    return render(request, 'core/teacher_profile.html', {
        'teacher': teacher,
        'subjects': teacher.subjects.all()
    })



@login_required
def add_subject(request):
    """Что делает: отображает форму и создаёт новый предмет преподавателя.
    Входные данные: request — GET-запрос или POST-запрос с данными предмета.
    Выходные данные: HTML-страница формы или редирект в профиль преподавателя.
    """
    teacher = TeacherProfile.objects.get(user=request.user)

    if request.method == 'POST':
        form = SubjectCreateForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            course = form.cleaned_data['course']
            institute = form.cleaned_data['institute']

            if Subject.objects.filter(name=name, course=course, institute=institute).exists():
                form.add_error(None, "Предмет уже существует")
            else:
                subject = form.save(commit=False)
                subject.teacher = teacher
                subject.save()
                return redirect('teacher_profile')
    else:
        form = SubjectCreateForm()

    return render(request, 'core/add_subject.html', {
        'form': form
    })


@login_required
def student_chat(request, subject_id):
    """Что делает: показывает чат, историю сообщений и документы предмета.
    Входные данные: request — HTTP-запрос; subject_id — идентификатор предмета.
    Выходные данные: HTML-страница чата, HTTP 403 или HTTP 404.
    """
    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return HttpResponseForbidden("Доступ только для студентов")

    subject = get_object_or_404(Subject, id=subject_id, students=student)
    
    messages_history = ChatMessage.objects.filter(
        student=student,
        subject=subject
    ).order_by("created_at")

    documents = [
        {"name": _document_display_name(document)}
        for document in Document.objects.filter(subject=subject).order_by("-uploaded_at")
    ]

    return render(request, "core/student_chat.html", {
        "subject": subject,
        "messages_history": messages_history,
        "documents": documents,
    })


@login_required
@require_http_methods(["POST"])
def send_message(request, subject_id):
    """Что делает: получает вопрос, формирует RAG-ответ и сохраняет сообщения.
    Входные данные: request — POST-запрос с JSON-полем question; subject_id — идентификатор предмета.
    Выходные данные: JSON с вопросом и ответом или JSON с ошибкой.
    """
    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return JsonResponse({"error": "Доступ запрещен"}, status=403)

    subject = get_object_or_404(Subject, id=subject_id, students=student)
    
    data = json.loads(request.body)
    question = data.get("question", "").strip()

    if not question:
        return JsonResponse({"error": "Введите вопрос"}, status=400)

    question_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=question,
        is_question=True
    )
    try:
        rag_result = answer_question(question=question, subject=subject)
        answer_text = rag_result["answer"]
        answer_sources = rag_result["sources"]
        answer_text = _append_sources_to_answer(answer_text, answer_sources)
    except Exception as e:
        answer_text = "Произошла ошибка при обработке запроса."
        answer_sources = []
        log_event(
            logger,
            logging.ERROR,
            "rag_answer_failed",
            subject_id=subject.id,
            student_id=student.id,
            question_length=len(question),
            error=str(e),
        )
        logger.exception("rag_answer_failed_exception")
    

    answer_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=answer_text,
        is_question=False,
        sources=answer_sources,
    )

    return JsonResponse({
        "success": True,
        "question": {
            "id": question_msg.id,
            "message": question_msg.message,
            "time": _message_time(question_msg.created_at)
        },
        "answer": {
            "id": answer_msg.id,
            "message": answer_msg.message,
            "time": _message_time(answer_msg.created_at),
            "sources": answer_msg.sources or [],
        }
    })


@login_required
@require_http_methods(["POST"])
def send_message_direct_llm(request, subject_id):
    """Что делает: получает вопрос, запрашивает прямой ответ LLM и сохраняет сообщения.
    Входные данные: request — POST-запрос с JSON-полем question; subject_id — идентификатор предмета.
    Выходные данные: JSON с вопросом и ответом или JSON с ошибкой.
    """
    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return JsonResponse({"error": "Доступ запрещен"}, status=403)

    subject = get_object_or_404(Subject, id=subject_id, students=student)

    data = json.loads(request.body)
    question = data.get("question", "").strip()

    if not question:
        return JsonResponse({"error": "Введите вопрос"}, status=400)

    question_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=question,
        is_question=True
    )

    try:
        prompt = (
            "Ты отвечаешь студенту в учебном веб-приложении. "
            "Дай краткий и понятный ответ на вопрос без использования внешнего контекста.\n\n"
            f"Вопрос: {question}"
        )
        answer_text = ask_gigachat(prompt)
    except Exception as e:
        answer_text = "Произошла ошибка при обработке запроса."
        log_event(
            logger,
            logging.ERROR,
            "direct_llm_answer_failed",
            subject_id=subject.id,
            student_id=student.id,
            question_length=len(question),
            error=str(e),
        )
        logger.exception("direct_llm_answer_failed_exception")

    answer_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=answer_text,
        is_question=False
    )

    return JsonResponse({
        "success": True,
        "question": {
            "id": question_msg.id,
            "message": question_msg.message,
            "time": _message_time(question_msg.created_at)
        },
        "answer": {
            "id": answer_msg.id,
            "message": answer_msg.message,
            "time": _message_time(answer_msg.created_at)
        }
    })
