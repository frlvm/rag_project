import chromadb
import logging
from django.conf import settings
from threading import Lock
from pathlib import Path
from .logging_utils import log_event


logger = logging.getLogger("core.rag")

class ChromaVectorStore:
    """
    Единый HTTP-клиент ChromaDB.
    Singleton-подход — клиент создаётся один раз.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self):
        self.chroma_host = settings.CHROMA_HOST
        self.chroma_port = settings.CHROMA_PORT
        self.chroma_ssl = settings.CHROMA_SSL

        self.client = chromadb.HttpClient(
            host=self.chroma_host,
            port=self.chroma_port,
            ssl=self.chroma_ssl,
        )

        self.collection = self.client.get_or_create_collection(
            name="subjects_collection"
        )

        log_event(
            logger,
            logging.INFO,
            "chroma_initialized",
            chroma_host=self.chroma_host,
            chroma_port=self.chroma_port,
            chroma_ssl=self.chroma_ssl,
            collection_name="subjects_collection",
            collection_count=self.collection.count(),
        )

    # -----------------------------
    # Добавление документов
    # -----------------------------
    def add_documents(self, ids, documents, embeddings, metadatas):
        if not ids:
            return

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

        log_event(
            logger,
            logging.INFO,
            "chroma_documents_added",
            added_count=len(ids),
            collection_count=self.collection.count(),
        )

    # -----------------------------
    # Поиск
    # -----------------------------
    def query(self, query_embedding, subject_id, top_k=5):
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"subject_id": str(subject_id)},
            include=["documents", "metadatas", "distances"]
        )

    def rebuild_subject_from_postgres(self, subject_id, batch_size=100):
        from core.models import TextChunk
        from core.services.embeddings import embed_text

        subject_id = str(subject_id)

        with self._lock:
            self.collection.delete(where={"subject_id": subject_id})

            chunks = (
                TextChunk.objects
                .filter(document__subject_id=subject_id)
                .select_related("document", "document__subject")
                .order_by("id")
            )
            total_chunks = chunks.count()
            processed = 0

            ids = []
            documents = []
            embeddings = []
            metadatas = []

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
                    self.collection.upsert(
                        ids=ids,
                        documents=documents,
                        embeddings=embeddings,
                        metadatas=metadatas,
                    )
                    processed += len(ids)
                    ids.clear()
                    documents.clear()
                    embeddings.clear()
                    metadatas.clear()

            if ids:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                processed += len(ids)

            log_event(
                logger,
                logging.WARNING,
                "chroma_subject_rebuilt_from_postgres",
                subject_id=subject_id,
                postgres_chunk_count=total_chunks,
                restored_chunk_count=processed,
            )

            return processed


    # -----------------------------
    # Удаление по предмету
    # -----------------------------
    def delete_by_document(self, document_id):
        self.collection.delete(
            where={"document_id": str(document_id)}
        )

    def delete_by_subject_and_title(self, subject_id, document_title):
        self.collection.delete(
            where={
                "$and": [
                    {"subject_id": str(subject_id)},
                    {"document_title": document_title}
                ]
            }
        )

    def reset_collection(self):
        with self._lock:
            collection_name = self.collection.name
            self.client.delete_collection(name=collection_name)
            self.collection = self.client.get_or_create_collection(
                name=collection_name
            )

            log_event(
                logger,
                logging.WARNING,
                "chroma_collection_reset",
                collection_name=collection_name,
                collection_count=self.collection.count(),
            )
