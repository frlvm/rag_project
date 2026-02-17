import os
import chromadb
from chromadb.config import Settings
from django.conf import settings
from threading import Lock


class ChromaVectorStore:
    """
    Единый persistent-клиент ChromaDB.
    Используется Singleton-подход, чтобы клиент создавался один раз.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        # Гарантируем один экземпляр на всё приложение
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Путь хранения
        self.chroma_path = os.path.join(settings.BASE_DIR, "chroma_storage")

        # Создаём папку, если её нет
        os.makedirs(self.chroma_path, exist_ok=True)

        # Persistent клиент
        self.client = chromadb.Client(
            Settings(
                persist_directory=self.chroma_path,
                anonymized_telemetry=False
            )
        )

        # Коллекция
        self.collection = self.client.get_or_create_collection(
            name="subjects_collection"
        )

        print(f"[Chroma] Initialized at {self.chroma_path}")

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

    # -----------------------------
    # Поиск
    # -----------------------------
    def query(self, query_embedding, subject_id, top_k=5):
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"subject_id": subject_id}
        )
        return results

    # -----------------------------
    # Удаление по предмету
    # -----------------------------
    def delete_by_subject(self, subject_id):
        self.collection.delete(
            where={"subject_id": subject_id}
        )

    # -----------------------------
    # Полная очистка (для тестов)
    # -----------------------------
    def reset_collection(self):
        self.client.delete_collection("subjects_collection")
        self.collection = self.client.get_or_create_collection(
            name="subjects_collection"
        )
