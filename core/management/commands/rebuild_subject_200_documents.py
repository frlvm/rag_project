import os
from itertools import cycle
from pathlib import Path
from time import perf_counter

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.models import Document, Subject, TextChunk
from core.services.embeddings import embed_text
from core.services.text_chunking import split_into_chunks
from core.services.text_cleaning import clean_text
from core.services.text_extraction import extract_text
from core.services.vector_store import ChromaVectorStore


DEFAULT_SOURCE_FILES = (
    "tests/fixtures/documents/small.pdf",
    "tests/fixtures/documents/medium.pdf",
    "tests/fixtures/documents/large.pdf",
)


class Command(BaseCommand):
    help = (
        "Удаляет документы выбранного предмета и заново наполняет его 200 "
        "документами на основе small/medium/large."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject-id",
            type=int,
            default=7,
            help="ID предмета для наполнения. По умолчанию: 7",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=200,
            help="Количество создаваемых документов. По умолчанию: 200",
        )
        parser.add_argument(
            "--source-files",
            default="|".join(DEFAULT_SOURCE_FILES),
            help="Исходные файлы через |. По умолчанию: small.pdf|medium.pdf|large.pdf из fixtures.",
        )

    def handle(self, *args, **options):
        started_at = perf_counter()
        subject = self._get_subject(options["subject_id"])
        count = options["count"]
        source_files = self._get_source_files(options["source_files"])
        vector_store = ChromaVectorStore()

        self.stdout.write(
            self.style.NOTICE(
                f"Предмет: {subject.id} — {subject.name}. "
                f"Будет создано документов: {count}."
            )
        )
        self.stdout.write(
            "Исходные файлы: " + ", ".join(path.name for path in source_files)
        )

        self._clear_subject_documents(subject, vector_store)
        prepared_sources = self._prepare_sources(source_files)
        created_documents, created_chunks = self._create_documents(
            subject=subject,
            count=count,
            prepared_sources=prepared_sources,
            vector_store=vector_store,
        )

        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Создано документов: {created_documents}; "
                f"создано чанков: {created_chunks}; время: {duration_ms} мс."
            )
        )

    def _get_subject(self, subject_id):
        try:
            return Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist as exc:
            raise CommandError(f"Предмет с ID {subject_id} не найден") from exc

    def _get_source_files(self, raw_value):
        source_files = []
        for item in raw_value.split("|"):
            item = item.strip()
            if not item:
                continue

            path = Path(item)
            if not path.is_absolute():
                path = Path(settings.BASE_DIR) / path
            if not path.exists():
                raise CommandError(f"Исходный файл не найден: {path}")
            source_files.append(path)

        if not source_files:
            raise CommandError("Не указаны исходные файлы")
        return source_files

    def _clear_subject_documents(self, subject, vector_store):
        documents = list(Document.objects.filter(subject=subject).only("id", "file", "title"))
        if not documents:
            self.stdout.write("Старых документов у предмета нет.")
            return

        self.stdout.write(f"Удаление старых документов: {len(documents)}")
        for index, document in enumerate(documents, start=1):
            vector_store.collection.delete(where={"document_id": str(document.id)})
            TextChunk.objects.filter(document=document).delete()
            document.file.delete(save=False)
            document.delete()

            if index % 25 == 0 or index == len(documents):
                self.stdout.write(f"Удалено документов: {index}/{len(documents)}")

    def _prepare_sources(self, source_files):
        prepared_sources = []
        embedding_cache = {}

        for source_file in source_files:
            units = extract_text(str(source_file))
            chunks = []

            for unit in units:
                cleaned_text = clean_text(unit.get("text", ""))
                if not cleaned_text:
                    continue

                for chunk_text in split_into_chunks(cleaned_text):
                    chunk_text = clean_text(chunk_text)
                    if not chunk_text:
                        continue

                    if chunk_text not in embedding_cache:
                        embedding_cache[chunk_text] = embed_text(chunk_text)

                    chunks.append({
                        "content": chunk_text,
                        "embedding": embedding_cache[chunk_text],
                        "page_start": unit.get("page_start"),
                        "page_end": unit.get("page_end"),
                    })

            if not chunks:
                raise CommandError(f"Не удалось извлечь текст из файла: {source_file}")

            prepared_sources.append({
                "path": source_file,
                "chunks": chunks,
            })
            self.stdout.write(
                f"Подготовлен источник {source_file.name}: чанков {len(chunks)}"
            )

        self.stdout.write(f"Уникальных эмбеддингов рассчитано: {len(embedding_cache)}")
        return prepared_sources

    def _create_documents(self, subject, count, prepared_sources, vector_store):
        created_documents = 0
        created_chunks = 0

        for index, source in zip(range(1, count + 1), cycle(prepared_sources)):
            source_path = source["path"]
            title = f"doc_{index:03d}_{source_path.stem}{source_path.suffix}"
            document = Document(title=title, subject=subject)

            with source_path.open("rb") as file_handle:
                document.file.save(title, File(file_handle), save=True)

            ids = []
            documents = []
            embeddings = []
            metadatas = []
            source_type = os.path.splitext(str(source_path))[1][1:]

            for chunk_index, chunk_data in enumerate(source["chunks"]):
                chunk = TextChunk.objects.create(
                    document=document,
                    content=chunk_data["content"],
                    page_start=chunk_data["page_start"],
                    page_end=chunk_data["page_end"],
                    chunk_index=chunk_index,
                )

                metadata = {
                    "chunk_id": str(chunk.id),
                    "document_id": str(document.id),
                    "document_title": str(document.title),
                    "subject_id": str(subject.id),
                    "chunk_index": chunk.chunk_index,
                    "source_type": source_type,
                }
                if chunk.page_start is not None:
                    metadata["page_start"] = chunk.page_start
                if chunk.page_end is not None:
                    metadata["page_end"] = chunk.page_end

                ids.append(str(chunk.id))
                documents.append(chunk.content)
                embeddings.append(chunk_data["embedding"])
                metadatas.append(metadata)

            vector_store.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            created_documents += 1
            created_chunks += len(ids)

            if index % 10 == 0 or index == count:
                self.stdout.write(
                    f"Создано документов: {index}/{count}; чанков всего: {created_chunks}"
                )

        return created_documents, created_chunks
