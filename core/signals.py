from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import StudentProfile, Subject
from core.services.subject_assignment import (
    assign_matching_students_to_subject,
    assign_matching_subjects_to_student,
)


@receiver(post_save, sender=StudentProfile)
def auto_assign_subjects_to_student(sender, instance, **kwargs):
    assign_matching_subjects_to_student(instance)


@receiver(post_save, sender=Subject)
def auto_assign_students_to_subject(sender, instance, **kwargs):
    assign_matching_students_to_subject(instance)
