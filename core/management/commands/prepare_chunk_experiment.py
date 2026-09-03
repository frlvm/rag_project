import importlib
import re
from pathlib import Path
from time import perf_counter

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.models import Document, Subject, TextChunk
from core.services.logging_utils import log_document_delete_event
from core.services.vector_store import ChromaVectorStore


PRESETS = {
    "1": (150, 0),
    "2": (300, 0),
    "3": (500, 100),
    "4": (1000, 200),
}


class Command(BaseCommand):
    help = (
        "Подготавливает эксперимент с chunk_size/chunk_overlap: меняет параметры, "
        "удаляет старый large.pdf у предмета и загружает его заново."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "preset",
            choices=PRESETS.keys(),
            help="Набор параметров: 1=150/0, 2=300/0, 3=500/100, 4=1000/200",
        )
        parser.add_argument(
            "--subject-id",
            type=int,
            default=None,
            help="ID предмета для эксперимента. Если не указан, используется название предмета.",
        )
        parser.add_argument(
            "--subject-name",
            default="Тестовый предмет 02",
            help="Название предмета для эксперимента. По умолчанию: Тестовый предмет 02",
        )
        parser.add_argument(
            "--file",
            default="tests/fixtures/documents/large.pdf",
            help="Путь к документу для повторной загрузки. По умолчанию: tests/fixtures/documents/large.pdf",
        )

    def handle(self, *args, **options):
        preset = options["preset"]
        subject_id = options["subject_id"]
        subject_name = options["subject_name"]
        source_file = Path(options["file"])
        if not source_file.is_absolute():
            source_file = Path(settings.BASE_DIR) / source_file

        if not source_file.exists():
            raise CommandError(f"Файл не найден: {source_file}")

        chunk_size, chunk_overlap = PRESETS[preset]
        self._update_chunking_settings(chunk_size, chunk_overlap)

        subject = self._get_subject(subject_id, subject_name)

        self.stdout.write(
            self.style.NOTICE(
                f"Параметры эксперимента: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
            )
        )

        self._delete_existing_large_documents(subject)
        document = self._create_document(subject, source_file)

        importlib.invalidate_caches()
        from core.services.document_processor import process_document

        process_document(document)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: large.pdf загружен заново для предмета {subject.id} ({subject.name}) "
                f"с chunk_size={chunk_size}, chunk_overlap={chunk_overlap}."
            )
        )
        self.stdout.write(
            "Если Django runserver был запущен, autoreload должен перезапустить сервер "
            "после изменения core/services/text_chunking.py."
        )

    def _update_chunking_settings(self, chunk_size, chunk_overlap):
        path = Path(settings.BASE_DIR) / "core" / "services" / "text_chunking.py"
        content = path.read_text(encoding="utf-8")
        content = re.sub(r"chunk_size=\d+", f"chunk_size={chunk_size}", content)
        content = re.sub(r"chunk_overlap=\d+", f"chunk_overlap={chunk_overlap}", content)
        path.write_text(content, encoding="utf-8")

    def _get_subject(self, subject_id, subject_name):
        if subject_id is not None:
            try:
                return Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist as exc:
                raise CommandError(f"Предмет с ID {subject_id} не найден") from exc

        matches = Subject.objects.filter(name=subject_name)
        if not matches.exists():
            raise CommandError(f"Предмет с названием '{subject_name}' не найден")

        if matches.count() > 1:
            ids = ", ".join(str(subject.id) for subject in matches)
            raise CommandError(
                f"Найдено несколько предметов с названием '{subject_name}': {ids}. "
                "Укажи нужный через --subject-id."
            )

        return matches.get()

    def _delete_existing_large_documents(self, subject):
        documents = Document.objects.filter(subject=subject, title="large.pdf")
        if not documents.exists():
            self.stdout.write("Старый large.pdf у предмета не найден, удаление пропущено.")
            return

        vector_store = ChromaVectorStore()

        for document in documents:
            started_at = perf_counter()
            document_data = {
                "document_id": document.id,
                "document_title": document.title,
                "file_path": document.file.path if document.file else "не указан",
                "file_size": document.file.size if document.file else 0,
                "subject_id": document.subject.id,
                "subject_name": document.subject.name,
                "teacher_name": document.subject.teacher.full_name,
            }

            chroma_chunks = vector_store.collection.get(
                where={"document_id": str(document.id)}
            )
            chroma_found_ids = [str(chunk_id) for chunk_id in chroma_chunks.get("ids", [])]
            vector_store.collection.delete(where={"document_id": str(document.id)})
            chroma_remaining_chunks = vector_store.collection.get(
                where={"document_id": str(document.id)}
            )
            chroma_remaining_ids = [
                str(chunk_id)
                for chunk_id in chroma_remaining_chunks.get("ids", [])
            ]

            chunks = TextChunk.objects.filter(document=document)
            postgresql_found_ids = [
                str(chunk_id)
                for chunk_id in chunks.values_list("id", flat=True)
            ]
            deleted_count, _ = chunks.delete()

            document.file.delete(save=False)
            document.delete()

            log_document_delete_event(
                document_data=document_data,
                postgresql_found_ids=postgresql_found_ids,
                postgresql_deleted_ids=postgresql_found_ids if deleted_count else [],
                chroma_found_ids=chroma_found_ids,
                chroma_deleted_ids=chroma_found_ids,
                chroma_remaining_ids=chroma_remaining_ids,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            )

    def _create_document(self, subject, source_file):
        document = Document(title=source_file.name, subject=subject)
        with source_file.open("rb") as file_handle:
            document.file.save(source_file.name, File(file_handle), save=True)
        return document
