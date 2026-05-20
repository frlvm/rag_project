from core.models import StudentProfile, Subject


def assign_matching_subjects_to_student(student: StudentProfile) -> int:
    matching_subject_ids = list(
        Subject.objects.filter(
            course=student.course,
            institute=student.institute,
        ).values_list("id", flat=True)
    )

    if not matching_subject_ids:
        return 0

    before_ids = set(student.subjects.values_list("id", flat=True))
    new_ids = [subject_id for subject_id in matching_subject_ids if subject_id not in before_ids]

    if not new_ids:
        return 0

    student.subjects.add(*new_ids)
    return len(new_ids)


def assign_matching_students_to_subject(subject: Subject) -> int:
    matching_student_ids = list(
        StudentProfile.objects.filter(
            course=subject.course,
            institute=subject.institute,
        ).values_list("id", flat=True)
    )

    if not matching_student_ids:
        return 0

    before_ids = set(subject.students.values_list("id", flat=True))
    new_ids = [student_id for student_id in matching_student_ids if student_id not in before_ids]

    if not new_ids:
        return 0

    subject.students.add(*new_ids)
    return len(new_ids)
