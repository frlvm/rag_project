from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, TeacherProfile, StudentProfile, Subject, Course, Institute


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
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user')
    search_fields = ('full_name', 'user__username')


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
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
    list_display = ['number', 'description']
    list_filter = ['number']
    search_fields = ['number', 'description']
    ordering = ['number']
    fieldsets = (
        (None, {
            'fields': ('number', 'description')
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