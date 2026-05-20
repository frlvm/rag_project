from django import forms

from .models import StudentProfile, Subject, User

from django import forms
from .models import Document, User, StudentProfile, Subject
from .services.subject_assignment import assign_matching_subjects_to_student


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'file']

        
class StudentRegistrationForm(forms.ModelForm):
    username = forms.CharField(label="Логин")
    password = forms.CharField(widget=forms.PasswordInput, label="Пароль")

    class Meta:
        model = StudentProfile
        fields = ('full_name', 'course', 'institute')

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password']
        )

        profile = super().save(commit=False)
        profile.user = user

        if commit:
            profile.save()
            assign_matching_subjects_to_student(profile)

        return profile
    

class SubjectCreateForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'course', 'institute']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Введите название предмета'
            }),
            'course': forms.Select(attrs={
                'class': 'form-input'
            }),
            'institute': forms.Select(attrs={
                'class': 'form-input'
            }),
        }
        labels = {
            'name': 'Название предмета',
            'course': 'Курс',
            'institute': 'Институт',
        }
