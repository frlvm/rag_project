from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.index, name='index'), 
    path('chat/<int:subject_id>/', views.student_chat, name='student_chat'),
    path('login/', views.CustomLoginView.as_view(
        template_name='core/login.html'
    ), name='login'),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path('register/student/', views.student_register, name='student_register'),
    path('student/profile/', views.student_profile, name='student_profile'),
    path('teacher/profile/', views.teacher_profile, name='teacher_profile'),
    path('teacher/subject/add/', views.add_subject, name='add_subject'),
    path('teacher/subject/<int:subject_id>/', views.subject_materials, name='subject_materials'),
    path('teacher/document/<int:doc_id>/delete/', views.delete_document, name='delete_document'), 
    path('student/subject/add', views.add_subject_for_student, name='add_subject_for_student'), 
]
