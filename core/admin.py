from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, TeacherProfile, StudentProfile, Subject, Course, Institute
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
import csv
from django import forms

from django.db import transaction

from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
import csv
from io import TextIOWrapper



def import_students_from_csv(request, csv_file):
    file = TextIOWrapper(csv_file.file, encoding='utf-8')
    reader = csv.DictReader(file)
    created_students = 0

    for row in reader:
        username = row.get("username")
        email = row.get("email")
        password = row.get("password") or "123456"
        full_name = row.get("full_name")
        course_number = row.get("course_number")
        course_level = row.get("course_level", "bachelor")
        institute_name = row.get("institute_name")

        if not all([username, email, full_name, course_number, institute_name]):
            continue

        # Создаём User
        user, is_created_user = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "role": "student"}
        )
        if is_created_user:
            user.set_password(password)
            user.save()

        # Создаём/берём Course
        course, _ = Course.objects.get_or_create(
            number=course_number,
            level=course_level,
            defaults={"description": f"{course_level.capitalize()} {course_number}-й курс"}
        )

        # Создаём/берём Institute
        institute, _ = Institute.objects.get_or_create(
            name=institute_name
        )

        # Создаём StudentProfile
        profile, _ = StudentProfile.objects.get_or_create(
            user=user,
            defaults={
                "full_name": full_name,
                "course": course,
                "institute": institute
            }
        )

        created_students += 1

    messages.success(request, f"Добавлено студентов: {created_students}")
    return redirect("..")

# -------------------
# Импорт преподавателей
# -------------------
def import_teachers_from_csv(request, csv_file):
    file = TextIOWrapper(csv_file.file, encoding='utf-8')
    reader = csv.DictReader(file)
    created_teachers = 0

    for row in reader:
        username = row.get("username")
        email = row.get("email")
        password = row.get("password") or "123456"
        full_name = row.get("full_name")

        if not all([username, email, full_name]):
            continue

        # Создаём User
        user, is_created_user = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "role": "teacher"}
        )
        if is_created_user:
            user.set_password(password)
            user.save()

        # Создаём TeacherProfile
        profile, _ = TeacherProfile.objects.get_or_create(
            user=user,
            defaults={"full_name": full_name}
        )

        created_teachers += 1

    messages.success(request, f"Добавлено преподавателей: {created_teachers}")
    return redirect("..")


class CSVUploadMixin:
    change_list_template = "admin/csv_upload_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("upload-csv/", self.admin_site.admin_view(self.upload_csv))
        ]
        return custom_urls + urls

    def upload_csv(self, request):
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            if not csv_file:
                messages.error(request, "Файл не выбран")
                return redirect(request.path)

            file = TextIOWrapper(csv_file.file, encoding='utf-8')
            reader = csv.DictReader(file)

            if "student" in request.path:
                return import_students_from_csv(request, csv_file)
            else:
                return import_teachers_from_csv(request, csv_file)

        return render(request, "admin/upload_csv.html")

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Роль пользователя', {'fields': ('role',)}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Роль пользователя', {'fields': ('role',)}),
    )

    list_display = ('username', 'email', 'role', 'is_staff')


@admin.register(TeacherProfile)
class TeacherProfileAdmin(CSVUploadMixin, admin.ModelAdmin):
    list_display = ('full_name', 'user')
    search_fields = ('full_name', 'user__username')


@admin.register(StudentProfile)
class StudentProfileAdmin(CSVUploadMixin, admin.ModelAdmin):
    list_display = ('full_name', 'user', 'course', 'institute')
    search_fields = ('full_name', 'user__username')
    list_filter = ('course', 'institute')

    filter_horizontal = ('subjects',)

    fieldsets = (
        (None, {
            'fields': ('user', 'full_name')
        }),
        ('Образование', {
            'fields': ('course', 'subjects', 'institute')
        }),
    )

@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'short_name', 'description']
    ordering = ['name']
    fieldsets = (
        (None, {
            'fields': ('name', 'short_name', 'description')
        }),
    )


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['number', 'level', 'description']
    list_filter = ['number']
    search_fields = ['number','level', 'description']
    ordering = ['number']
    fieldsets = (
        (None, {
            'fields': ('number', 'level', 'description')
        }),
    )


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'teacher', 'course', 'institute']
    list_filter = ['course', 'institute', 'teacher']
    search_fields = ['name']
    ordering = ['name']
    fieldsets = (
        (None, {
            'fields': ('name', 'teacher')
        }),
        ('Детали', {
            'fields': ('course', 'institute')
        }),
    )