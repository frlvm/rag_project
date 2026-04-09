from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from .forms import DocumentForm, StudentRegistrationForm, SubjectCreateForm
from .models import Document, Subject, StudentProfile, TeacherProfile, ChatMessage, Course, Institute, TextChunk, User
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from core.services.rag_pipeline import answer_question
from core.services.text_extraction import extract_text
from core.services.text_cleaning import clean_text
from core.services.text_chunking import split_into_chunks
from core.services.document_processor import process_document
from django.http import HttpResponseForbidden, HttpResponse
from django.urls import reverse
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
from core.services.retriever import retrieve_chunks, normalize_sources
from django import forms
import csv
from core.services.vector_store import ChromaVectorStore  # проверь путь
from django.contrib.auth import authenticate, login


class CustomLoginView(LoginView):
    template_name = "core/login.html"

    def form_invalid(self, form):
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
        user = self.request.user

        if user.role == 'teacher':
            return reverse('teacher_profile')
        return reverse('student_profile')

@login_required
def delete_document(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)

    if document.subject.teacher.user != request.user:
        return HttpResponseForbidden("Нет доступа")

    subject_id = document.subject.id

    vector_store = ChromaVectorStore()

    # 🔥 1. Удаляем из Chroma ТОЛЬКО этот документ
    vector_store.collection.delete(
        where={"document_id": str(document.id)}
    )

    # 🔥 2. Удаляем чанки из БД
    chunks = TextChunk.objects.filter(document=document)
    deleted_count, _ = chunks.delete()

    # 🔥 3. Удаляем файл и документ
    document.file.delete(save=False)
    document.delete()

    messages.success(
        request,
        f"Документ удалён. Чанков: {deleted_count}"
    )

    return redirect("subject_materials", subject_id=subject_id)


@login_required
def subject_materials(request, subject_id):
    # проверка преподавателя
    try:
        teacher = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return HttpResponseForbidden("Доступ только для преподавателей")

    subject = get_object_or_404(
        Subject,
        id=subject_id,
        teacher=teacher
    )

    # загрузка документа
    if request.method == "POST":
        file = request.FILES.get("file")

        if file:
            document = Document.objects.create(
                title=file.name,
                file=file,
                subject=subject
            )

            # RAG-подготовка
            process_document(document)

            return redirect("subject_materials", subject_id=subject.id)

    # список документов
    documents = subject.documents.all().order_by("-uploaded_at")

    return render(request, "core/subject_materials.html", {
        "subject": subject,
        "documents": documents
    })






@login_required
def index(request):
    if request.user.role == 'teacher':
        return redirect('/teacher/profile/')
    return redirect('/student/profile/')


def student_register(request):
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
    student = StudentProfile.objects.get(user=request.user)

    return render(request, 'core/student_profile.html', {
        'student': student,
        'subjects': student.subjects.all()
    })


@login_required
def teacher_profile(request):
    teacher = TeacherProfile.objects.get(user=request.user)

    return render(request, 'core/teacher_profile.html', {
        'teacher': teacher,
        'subjects': teacher.subjects.all()
    })



@login_required
def add_subject(request):
    teacher = TeacherProfile.objects.get(user=request.user)

    if request.method == 'POST':
        form = SubjectCreateForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            course = form.cleaned_data['course']
            institute = form.cleaned_data['institute']

            # 🔒 Проверка на существующий предмет
            if Subject.objects.filter(name=name, course=course, institute=institute).exists():
                messages.error(request, "Предмет уже существует")
            else:
                subject = form.save(commit=False)
                subject.teacher = teacher
                subject.save()
                messages.success(request, "Предмет успешно добавлен")
                return redirect('teacher_profile')
    else:
        form = SubjectCreateForm()

    return render(request, 'core/add_subject.html', {
        'form': form
    })


@login_required
def add_subject_for_student(request):
    student = StudentProfile.objects.get(user=request.user)

    allowed_subjects = Subject.objects.filter(
        course=student.course,
        institute=student.institute
    ).exclude(
        students=student
    )

    if request.method == 'POST':
        subject_id = request.POST.get('subject_id')

        subject = Subject.objects.filter(
            id=subject_id,
            course=student.course,
            institute=student.institute
        ).first()

        if not subject:
            return HttpResponseForbidden("Нельзя добавить этот предмет")

        student.subjects.add(subject)
        return redirect('student_profile')

    return render(request, 'core/add_subject_student.html', {
        'subjects': allowed_subjects
    })

@login_required
def student_chat(request, subject_id):
    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return HttpResponseForbidden("Доступ только для студентов")

    subject = get_object_or_404(Subject, id=subject_id, students=student)
    
    # История сообщений
    messages_history = ChatMessage.objects.filter(
        student=student,
        subject=subject
    ).order_by("created_at")

    documents = Document.objects.filter(subject=subject)

    return render(request, "core/student_chat.html", {
        "subject": subject,
        "messages_history": messages_history,
        "documents": documents,
    })


# НОВАЯ view - для AJAX запросов
@login_required
@require_http_methods(["POST"])  # Только POST запросы
def send_message(request, subject_id):
    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return JsonResponse({"error": "Доступ запрещен"}, status=403)

    subject = get_object_or_404(Subject, id=subject_id, students=student)
    
    # Получаем вопрос из AJAX запроса
    data = json.loads(request.body)
    question = data.get("question", "").strip()

    if not question:
        return JsonResponse({"error": "Введите вопрос"}, status=400)

    # Сохраняем вопрос студента
    question_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=question,
        is_question=True
    )
    try:
        # Получаем ответ от RAG системы
        answer_text = answer_question(question=question, subject=subject)
    except Exception as e:
        answer_text = "Произошла ошибка при обработке запроса."
        print(f"RAG Error: {e}")  # Логируем ошибку
    

    # Сохраняем ответ системы
    answer_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=answer_text,
        is_question=False
    )

    # Возвращаем JSON с обоими сообщениями
    return JsonResponse({
        "success": True,
        "question": {
            "id": question_msg.id,
            "message": question_msg.message,
            "time": question_msg.created_at.strftime("%H:%M")
        },
        "answer": {
            "id": answer_msg.id,
            "message": answer_msg.message,
            "time": answer_msg.created_at.strftime("%H:%M")
        }
    })

