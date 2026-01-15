from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.index, name='index'), 
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/upload/', views.upload_document, name='upload_document'),
    path('chat/', views.student_chat, name='student_chat'),
    path('login/', auth_views.LoginView.as_view(
        template_name='core/login.html'
    ), name='login'),
]
