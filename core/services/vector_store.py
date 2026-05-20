import os
import chromadb
import logging
from django.conf import settings
from threading import Lock
import shutil
from .logging_utils import log_event


logger = logging.getLogger("core.rag")

class ChromaVectorStore:
    """
    Единый persistent-клиент ChromaDB.
    Singleton-подход — клиент создаётся один раз.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Папка хранения
        self.chroma_path = os.path.join(settings.BASE_DIR, "chroma_storage")
        os.makedirs(self.chroma_path, exist_ok=True)

        # Persistent клиент
        self.client = chromadb.PersistentClient(
            path=self.chroma_path
        )

        # Коллекция
        self.collection = self.client.get_or_create_collection(
            name="subjects_collection"
        )

        log_event(
            logger,
            logging.INFO,
            "chroma_initialized",
            chroma_path=self.chroma_path,
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

    # -----------------------------
    # Полная очистка
    # -----------------------------
    def reset_collection(self):
    # 1. Закрыть/забыть текущую коллекцию
        self.collection = None

    # 2. Удалить директорию Chroma
        persist_dir = "./chroma_db"  # ← укажи свой путь

        if os.path.exists(persist_dir):
            shutil.rmtree(persist_dir)
            log_event(
                logger,
                logging.WARNING,
                "chroma_directory_removed",
                persist_dir=persist_dir,
            )

    # 3. Создать новый клиент
        import chromadb
        from chromadb.config import Settings

        self.client = chromadb.Client(
            Settings(persist_directory=persist_dir)
        )

    # 4. Создать коллекцию заново
        self.collection = self.client.get_or_create_collection(
            name="subjects_collection"
        )

        data = self.collection.get()
        log_event(
            logger,
            logging.WARNING,
            "chroma_collection_reset",
            collection_name="subjects_collection",
            collection_count=len(data["ids"]),
        )
