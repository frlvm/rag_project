from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import DocumentForm
from .models import Document
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User
from core.services.rag_pipeline import answer_question
from core.services.text_extraction import extract_text
from core.services.text_cleaning import clean_text
from core.services.text_chunking import split_into_chunks
from core.services.document_processor import process_document


@login_required
def upload_document(request):
    if request.user.role != "teacher":
        return redirect("login")

    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.uploaded_by = request.user
            document.save()

            # 🔹 полный pipeline
            raw_text = extract_text(document.file.path)
            cleaned = clean_text(raw_text)
            chunks = split_into_chunks(cleaned)

            process_document(document, chunks)

            return redirect("teacher_dashboard")
    else:
        form = DocumentForm()

    return render(request, "core/upload_document.html", {"form": form})


@login_required
def teacher_dashboard(request):
    if request.user.role != 'teacher':
        return redirect('login')

    documents = Document.objects.filter(uploaded_by=request.user)

    return render(request, 'core/teacher_dashboard.html', {
        'documents': documents
    })


@login_required
def student_chat(request):
    if request.user.role != "student":
        return redirect("login")

    answer = None

    if request.method == "POST":
        question = request.POST.get("question")
        if question:
            answer = answer_question(question)

    return render(request, "core/student_chat.html", {
        "answer": answer
    })


@login_required
def index(request):
    if request.user.role == 'teacher':
        return redirect('teacher_dashboard')
    return redirect('student_chat')


def chat_view(request):
    if request.method == "POST":
        question = request.POST.get("question")
        answer = answer_question(question)
        return render(request, "student_chat.html", {"answer": answer})

    return render(request, "student_chat.html")