from pathlib import Path
from time import perf_counter

from django.core.management.base import BaseCommand

from core.models import TextChunk
from core.services.embeddings import embed_text
from core.services.vector_store import ChromaVectorStore


class Command(BaseCommand):
    help = "Пересоздаёт коллекцию ChromaDB из чанков, сохранённых в PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Размер пачки для записи в ChromaDB. По умолчанию: 100",
        )

    def handle(self, *args, **options):
        started_at = perf_counter()
        batch_size = options["batch_size"]
        vector_store = ChromaVectorStore()

        collection_name = vector_store.collection.name
        self.stdout.write(f"Пересоздание коллекции ChromaDB: {collection_name}")

        vector_store.reset_collection()

        chunks = (
            TextChunk.objects
            .select_related("document", "document__subject")
            .order_by("id")
        )
        total_chunks = chunks.count()
        self.stdout.write(f"Чанков в PostgreSQL: {total_chunks}")

        ids = []
        documents = []
        embeddings = []
        metadatas = []
        processed = 0

        for chunk in chunks.iterator(chunk_size=batch_size):
            document = chunk.document
            file_path = document.file.name if document.file else document.title
            source_type = Path(file_path).suffix.lower().lstrip(".")

            metadata = {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_title": str(document.title),
                "subject_id": str(document.subject.id),
                "chunk_index": chunk.chunk_index,
                "source_type": source_type,
            }
            if chunk.page_start is not None:
                metadata["page_start"] = chunk.page_start
            if chunk.page_end is not None:
                metadata["page_end"] = chunk.page_end

            ids.append(str(chunk.id))
            documents.append(chunk.content)
            embeddings.append(embed_text(chunk.content))
            metadatas.append(metadata)

            if len(ids) >= batch_size:
                vector_store.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                processed += len(ids)
                self.stdout.write(f"Восстановлено чанков: {processed}/{total_chunks}")
                ids.clear()
                documents.clear()
                embeddings.clear()
                metadatas.clear()

        if ids:
            vector_store.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            processed += len(ids)
            self.stdout.write(f"Восстановлено чанков: {processed}/{total_chunks}")

        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        self.stdout.write(
            self.style.SUCCESS(
                f"ChromaDB пересоздана. Чанков: {processed}; время: {duration_ms} мс."
            )
        )
