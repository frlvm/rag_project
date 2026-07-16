from datetime import datetime
from pathlib import Path
from time import perf_counter

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from core.models import Document, Subject, TextChunk
from core.services.rag_pipeline import answer_question
from core.services.vector_store import ChromaVectorStore


DEFAULT_PRESETS = (
    (150, 0),
    (300, 50),
    (500, 100),
    (800, 150),
)

DEFAULT_QUESTIONS = (
    ("Определение", "Что такое защитное заземление?"),
    ("Сравнение", "Чем защитное заземление отличается от рабочего и молниезащитного?"),
    ("Причина", "Почему защитное заземление снижает напряжение прикосновения?"),
    ("Классификация", "Какие виды заземления выделяются в документе?"),
    ("Отсутствующий ответ", "Какова стоимость обучения в университете в 2026 году?"),
)


class Command(BaseCommand):
    help = (
        "Runs chunking parameter experiment: reindexes one document with several "
        "chunk_size/chunk_overlap presets, asks questions, and writes answers to txt."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject-id",
            type=int,
            default=None,
            help="Subject ID for experiment. If omitted, --subject-name is used.",
        )
        parser.add_argument(
            "--subject-name",
            default="Тестовый предмет 02",
            help="Subject name for experiment. Default: Тестовый предмет 02.",
        )
        parser.add_argument(
            "--file",
            default="tests/fixtures/documents/large.pdf",
            help="Document path to reload for each preset.",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Output txt path. Default: reports/chunk_experiment_<timestamp>.txt.",
        )
        parser.add_argument(
            "--presets",
            default=",".join(f"{size}:{overlap}" for size, overlap in DEFAULT_PRESETS),
            help="Comma-separated presets, for example: 150:0,300:50,500:100,800:150.",
        )
        parser.add_argument(
            "--top-k",
            type=int,
            default=5,
            help="Number of retrieved chunks for every question. Default: 5.",
        )
        parser.add_argument(
            "--questions-file",
            default=None,
            help=(
                "Optional UTF-8 txt file with questions. Each line can be "
                "'type|question' or just 'question'."
            ),
        )
        parser.add_argument(
            "--clear-subject",
            action="store_true",
            help="Delete all documents from the subject before each preset. By default only the experiment file title is deleted.",
        )

    def handle(self, *args, **options):
        subject = self._get_subject(options["subject_id"], options["subject_name"])
        source_file = self._resolve_source_file(options["file"])
        presets = self._parse_presets(options["presets"])
        questions = self._load_questions(options["questions_file"])
        output_path = self._resolve_output_path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        results = {
            index: []
            for index in range(1, len(questions) + 1)
        }

        report_meta = {
            "subject": subject,
            "source_file": source_file,
            "presets": presets,
            "questions": questions,
            "started_at": datetime.now(),
            "top_k": options["top_k"],
        }

        self._write_report(output_path, report_meta, results)
        self.stdout.write(self.style.NOTICE(f"Report: {output_path}"))

        for chunk_size, chunk_overlap in presets:
            preset_label = f"{chunk_size}/{chunk_overlap}"
            self.stdout.write(
                self.style.NOTICE(
                    f"Preset {preset_label}: reload document and build index"
                )
            )

            preset_started_at = perf_counter()
            try:
                with override_settings(
                    RAG_CHUNK_SIZE=chunk_size,
                    RAG_CHUNK_OVERLAP=chunk_overlap,
                ):
                    document = self._reload_document(
                        subject=subject,
                        source_file=source_file,
                        clear_subject=options["clear_subject"],
                    )
                    document.refresh_from_db()

                    chunk_count = TextChunk.objects.filter(document=document).count()
                    for question_index, (question_type, question) in enumerate(questions, start=1):
                        answer_started_at = perf_counter()
                        result = answer_question(
                            question=question,
                            subject=subject,
                            top_k=options["top_k"],
                        )
                        answer_duration_ms = round((perf_counter() - answer_started_at) * 1000, 2)

                        results[question_index].append({
                            "preset": preset_label,
                            "chunk_size": chunk_size,
                            "chunk_overlap": chunk_overlap,
                            "chunk_count": chunk_count,
                            "answer": result["answer"],
                            "sources": result["sources"],
                            "metadatas": result.get("metadatas", []),
                            "duration_ms": answer_duration_ms,
                            "error": None,
                        })

                        self.stdout.write(
                            f"  Q{question_index}: done in {answer_duration_ms} ms"
                        )
                        self._write_report(output_path, report_meta, results)

            except Exception as exc:
                for question_index in results:
                    results[question_index].append({
                        "preset": preset_label,
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                        "chunk_count": None,
                        "answer": "",
                        "sources": [],
                        "metadatas": [],
                        "duration_ms": None,
                        "error": str(exc),
                    })
                self._write_report(output_path, report_meta, results)
                self.stdout.write(self.style.ERROR(f"Preset {preset_label} failed: {exc}"))
                continue

            preset_duration_ms = round((perf_counter() - preset_started_at) * 1000, 2)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Preset {preset_label}: completed in {preset_duration_ms} ms"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Done. Results saved to {output_path}"))

    def _get_subject(self, subject_id, subject_name):
        if subject_id is not None:
            try:
                return Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist as exc:
                raise CommandError(f"Subject with ID {subject_id} not found") from exc

        matches = Subject.objects.filter(name=subject_name)
        if not matches.exists():
            raise CommandError(f"Subject named '{subject_name}' not found")
        if matches.count() > 1:
            ids = ", ".join(str(subject.id) for subject in matches)
            raise CommandError(
                f"Several subjects named '{subject_name}' found: {ids}. Use --subject-id."
            )
        return matches.get()

    def _resolve_source_file(self, raw_path):
        source_file = Path(raw_path)
        if not source_file.is_absolute():
            source_file = Path(settings.BASE_DIR) / source_file
        if not source_file.exists():
            raise CommandError(f"Source file not found: {source_file}")
        return source_file

    def _resolve_output_path(self, raw_path):
        if raw_path:
            output_path = Path(raw_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(settings.BASE_DIR) / "reports" / f"chunk_experiment_{timestamp}.txt"

        if not output_path.is_absolute():
            output_path = Path(settings.BASE_DIR) / output_path
        return output_path

    def _parse_presets(self, raw_value):
        presets = []
        for item in raw_value.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                chunk_size, chunk_overlap = item.split(":", maxsplit=1)
                presets.append((int(chunk_size), int(chunk_overlap)))
            except ValueError as exc:
                raise CommandError(
                    f"Invalid preset '{item}'. Expected format: chunk_size:chunk_overlap"
                ) from exc

        if not presets:
            raise CommandError("At least one preset is required")
        return presets

    def _load_questions(self, raw_path):
        if not raw_path:
            return list(DEFAULT_QUESTIONS)

        questions_file = Path(raw_path)
        if not questions_file.is_absolute():
            questions_file = Path(settings.BASE_DIR) / questions_file
        if not questions_file.exists():
            raise CommandError(f"Questions file not found: {questions_file}")

        questions = []
        for line in questions_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "|" in line:
                question_type, question = line.split("|", maxsplit=1)
            else:
                question_type, question = "Вопрос", line
            questions.append((question_type.strip(), question.strip()))

        if not questions:
            raise CommandError("Questions file contains no questions")
        return questions

    def _reload_document(self, subject, source_file, clear_subject):
        vector_store = ChromaVectorStore()

        if clear_subject:
            documents = list(Document.objects.filter(subject=subject))
        else:
            documents = list(Document.objects.filter(subject=subject, title=source_file.name))

        for document in documents:
            vector_store.collection.delete(where={"document_id": str(document.id)})
            TextChunk.objects.filter(document=document).delete()
            document.file.delete(save=False)
            document.delete()

        document = Document(title=source_file.name, subject=subject)
        with source_file.open("rb") as file_handle:
            document.file.save(source_file.name, File(file_handle), save=True)

        from core.services.document_processor import process_document

        process_document(document)
        return document

    def _write_report(self, output_path, meta, results):
        lines = [
            "Эксперимент 4.5: сравнение параметров чанкирования",
            "=" * 72,
            f"Дата запуска: {meta['started_at'].strftime('%d.%m.%Y %H:%M:%S')}",
            f"Предмет: {meta['subject'].id} — {meta['subject'].name}",
            f"Документ: {meta['source_file']}",
            "Параметры: " + ", ".join(
                f"{size}/{overlap}" for size, overlap in meta["presets"]
            ),
            f"top_k: {meta['top_k']}",
            "",
            "Вопросы:",
        ]

        for index, (question_type, question) in enumerate(meta["questions"], start=1):
            lines.append(f"{index}. [{question_type}] {question}")

        lines.extend(["", "=" * 72, "Ответы по вопросам"])

        for question_index, (question_type, question) in enumerate(meta["questions"], start=1):
            lines.extend([
                "",
                "-" * 72,
                f"Вопрос {question_index}. Тип: {question_type}",
                question,
            ])

            for result in results.get(question_index, []):
                lines.extend([
                    "",
                    f"Параметры: chunk_size/chunk_overlap = {result['preset']}",
                    f"Количество чанков: {result['chunk_count']}",
                    f"Время ответа: {result['duration_ms']} мс",
                ])

                if result["error"]:
                    lines.append(f"ОШИБКА: {result['error']}")
                    continue

                lines.extend([
                    "Ответ:",
                    result["answer"],
                    "Дистанции найденных фрагментов:",
                    self._format_distances(result["metadatas"]),
                    "Источники:",
                    self._format_sources(result["sources"]),
                ])

        output_path.write_text("\n".join(lines), encoding="utf-8")

    def _format_sources(self, sources):
        if not sources:
            return "нет"

        formatted = []
        for source in sources:
            title = source.get("document_title") or "без названия"
            page_start = source.get("page_start")
            page_end = source.get("page_end")

            if page_start and page_end and page_start != page_end:
                formatted.append(f"- {title}, стр. {page_start}-{page_end}")
            elif page_start:
                formatted.append(f"- {title}, стр. {page_start}")
            else:
                formatted.append(f"- {title}")

        return "\n".join(formatted)

    def _format_distances(self, metadatas):
        if not metadatas:
            return "нет"

        distances = []
        for index, metadata in enumerate(metadatas, start=1):
            distance = metadata.get("distance")
            if distance is None:
                continue
            distances.append(f"{index}. {distance:.4f}")

        return "\n".join(distances) if distances else "нет"
