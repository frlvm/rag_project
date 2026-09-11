from django.db import migrations


def sync_user_roles_with_profiles(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(studentprofile__isnull=False).update(role="student")
    User.objects.filter(teacherprofile__isnull=False).update(role="teacher")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_alter_course_options_course_level_and_more"),
    ]

    operations = [
        migrations.RunPython(
            sync_user_roles_with_profiles,
            migrations.RunPython.noop,
        ),
    ]
