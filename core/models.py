from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.db.models import JSONField


class User(AbstractUser):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)


# Добавьте эти модели к существующим
class Institute(models.Model):
    """Модель для хранения институтов"""
    name = models.CharField(
        max_length=200,
        verbose_name="Название института",
        unique=True
    )
    short_name = models.CharField(
        max_length=50,
        verbose_name="Короткое название",
        blank=True
    )
    description = models.TextField(
        verbose_name="Описание",
        blank=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    
    class Meta:
        verbose_name = "Институт"
        verbose_name_plural = "Институты"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Course(models.Model):
    """Модель для хранения курсов"""
    number = models.IntegerField(
        verbose_name="Номер курса",
        unique=True
    )
    description = models.CharField(
        max_length=100,
        verbose_name="Описание",
        blank=True
    )
    
    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ['number']
    
    def __str__(self):
        return f"{self.number} курс"


class Subject(models.Model):
    name = models.CharField(max_length=255)
    course = models.ForeignKey(
        Course,
        on_delete=models.PROTECT,
        verbose_name="Курс"
    )
    institute = models.ForeignKey(
        Institute,
        on_delete=models.PROTECT,
        verbose_name="Институт"
    )
    teacher = models.ForeignKey(
        'TeacherProfile',
        on_delete=models.CASCADE,
        related_name='subjects'
    )

    def __str__(self):
        return f"{self.name} — {self.course} курс ({self.institute})"


class Document(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='documents'
    )

    def __str__(self):
        return self.title


class TextChunk(models.Model):
    document = models.ForeignKey(
        Document,
        related_name="chunks",
        on_delete=models.CASCADE
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # на будущее
    embedding = models.JSONField(null=True, blank=True)


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    course = models.ForeignKey(
        Course, 
        on_delete=models.PROTECT,
        verbose_name="Курс",
        related_name='students'
    )
    
    institute = models.ForeignKey(
        Institute,
        on_delete=models.PROTECT,
        verbose_name="Институт",
        related_name='students'
    )

    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name='students'
    )

    def __str__(self):
        return self.full_name


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)

    def __str__(self):
        return self.full_name


class ChatMessage(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    message = models.TextField()
    is_question = models.BooleanField()  # True — вопрос, False — ответ
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        role = "Q" if self.is_question else "A"
        return f"{role}: {self.message[:50]}"


