from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import DocumentForm, StudentRegistrationForm, SubjectCreateForm
from .models import Document, Subject, StudentProfile, TeacherProfile, ChatMessage
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

class CustomLoginView(LoginView):
    template_name = "core/login.html"

    def get_success_url(self):
        user = self.request.user

        if user.role == 'teacher':
            return reverse('teacher_profile')
        return reverse('student_profile')


@login_required
def delete_document(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)

    # 🔒 проверка владельца
    if document.subject.teacher.user != request.user:
        return HttpResponseForbidden("Нет доступа")

    subject_id = document.subject.id

    # удаляем файл + запись + чанки
    document.file.delete(save=False)
    document.delete()

    return redirect("subject_materials", subject_id=subject_id)


@login_required
def subject_materials(request, subject_id):
    # 🔒 проверка преподавателя
    try:
        teacher = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return HttpResponseForbidden("Доступ только для преподавателей")

    subject = get_object_or_404(
        Subject,
        id=subject_id,
        teacher=teacher
    )

    # 📤 загрузка документа
    if request.method == "POST":
        file = request.FILES.get("file")

        if file:
            document = Document.objects.create(
                title=file.name,
                file=file,
                subject=subject
            )

            # 🔥 RAG-подготовка
            process_document(document)

            return redirect("subject_materials", subject_id=subject.id)

    # 📄 список документов
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
    # 1️⃣ профиль студента
    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return HttpResponseForbidden("Доступ только для студентов")

    # 2️⃣ предмет + проверка доступа
    subject = get_object_or_404(
        Subject,
        id=subject_id,
        students=student
    )

    # 3️⃣ история чата (по предмету!)
    messages_history = ChatMessage.objects.filter(
        student=student,
        subject=subject
    ).order_by("created_at")

    # 4️⃣ документы предмета (для сайдбара)
    documents = Document.objects.filter(subject=subject)

    error = None

    # 5️⃣ обработка вопроса
    if request.method == "POST":
        question = request.POST.get("question", "").strip()

        if not question:
            error = "Введите вопрос"
        else:
            # сохраняем вопрос
            ChatMessage.objects.create(
                student=student,
                subject=subject,
                message=question,
                is_question=True
            )

            try:
                # 🔥 RAG ПО ПРЕДМЕТУ
                answer = answer_question(
                    question=question,
                    subject=subject
                )

            except Exception as e:
                answer = "Произошла ошибка при обработке запроса."
                error = str(e)

            # сохраняем ответ
            ChatMessage.objects.create(
                student=student,
                subject=subject,
                message=answer,
                is_question=False
            )

            # обновляем историю
            messages_history = ChatMessage.objects.filter(
                student=student,
                subject=subject
            ).order_by("created_at")

    return render(request, "core/student_chat.html", {
        "subject": subject,
        "messages_history": messages_history,
        "documents": documents,
        "error": error
    })