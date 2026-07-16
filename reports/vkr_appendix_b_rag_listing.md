# Приложение Б. Листинг основных модулей RAG-конвейера

В приложении приведены ключевые фрагменты программного кода, относящиеся к
реализации RAG-конвейера: загрузка и извлечение текста из документов,
очистка, чанкирование, построение эмбеддингов, запись в ChromaDB, поиск
релевантных фрагментов с учетом порога релевантности, формирование промта,
обращение к GigaChat и сохранение ответа пользователю. Служебное логирование,
оформление интерфейса и вспомогательные обработчики, не влияющие на алгоритм
RAG, в листинге опущены.

## `rag_project/settings.py`

```python
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")

RAG_RELEVANCE_DISTANCE_THRESHOLD = float(
    os.getenv("RAG_RELEVANCE_DISTANCE_THRESHOLD", "0.45")
)
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "300"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
```

## `core/models.py`

```python
# Класс реализует учебный предмет, к которому привязаны документы и сообщения.
class Subject(models.Model):
    name = models.CharField(max_length=255)
    course = models.ForeignKey(Course, on_delete=models.PROTECT)
    institute = models.ForeignKey(Institute, on_delete=models.PROTECT)
    teacher = models.ForeignKey("TeacherProfile", on_delete=models.CASCADE,
                                related_name="subjects")


# Класс реализует загруженный преподавателем учебный документ.
class Document(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                related_name="documents")


# Класс реализует текстовый фрагмент документа после чанкирования.
class TextChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE,
                                 related_name="chunks")
    content = models.TextField()
    page_start = models.IntegerField(null=True, blank=True)
    page_end = models.IntegerField(null=True, blank=True)
    chunk_index = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


# Класс реализует сохранение вопроса студента или ответа системы.
class ChatMessage(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE,
                                related_name="messages")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE,
                                related_name="messages")
    message = models.TextField()
    is_question = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sources = models.JSONField(null=True, blank=True)
```

## `core/services/text_extraction.py`

```python
import os
import fitz
from docx import Document as DocxDocument
from docx.document import Document as DocxDocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


# Класс реализует ошибку извлечения текста из документа.
class TextExtractionError(Exception):
    pass


# Функция определяет формат файла и запускает подходящий способ извлечения текста.
def extract_text(file_path: str) -> list[dict]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    if ext == ".docx":
        return extract_text_from_docx(file_path)

    raise ValueError("Неподдерживаемый формат файла")


# Функция извлекает текст из PDF постранично и запускает OCR для сканов.
def extract_text_from_pdf(file_path: str) -> list[dict]:
    units = []
    with fitz.open(file_path) as pdf:
        for i, page in enumerate(pdf, start=1):
            units.append({
                "page_start": i,
                "page_end": i,
                "text": page.get_text(),
            })

    if any(unit["text"].strip() for unit in units):
        return units

    return extract_text_from_scanned_pdf(file_path)


# Функция выполняет OCR-распознавание сканированного PDF-документа.
def extract_text_from_scanned_pdf(file_path: str) -> list[dict]:
    language = os.getenv("RAG_OCR_LANGUAGE", "rus+eng")
    dpi = int(os.getenv("RAG_OCR_DPI", "200"))
    units = []

    try:
        with fitz.open(file_path) as pdf:
            for i, page in enumerate(pdf, start=1):
                text_page = page.get_textpage_ocr(
                    language=language,
                    dpi=dpi,
                    full=True,
                )
                units.append({
                    "page_start": i,
                    "page_end": i,
                    "text": page.get_text("text", textpage=text_page),
                })
    except Exception as exc:
        raise TextExtractionError(
            "Не удалось выполнить OCR для сканированного PDF. "
            "Установите Tesseract OCR и языковые пакеты rus+eng."
        ) from exc

    return units


# Функция последовательно обходит абзацы и таблицы DOCX-документа.
def _iter_block_items(parent):
    parent_element = parent.element.body if isinstance(
        parent, DocxDocumentType
    ) else parent._element

    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


# Функция извлекает текст абзаца DOCX и дополнительно выделяет заголовки.
def _extract_paragraph_text(paragraph):
    text = paragraph.text.strip()
    if not text:
        return ""

    style_name = paragraph.style.name.lower() if paragraph.style else ""
    if "heading" in style_name or "заголов" in style_name:
        return f"{text}."
    return text


# Функция преобразует строки таблицы DOCX в текстовое представление.
def _extract_table_text(table):
    rows = []
    for row in table.rows:
        cells = [
            " ".join(part.strip() for part in cell.text.splitlines()
                     if part.strip())
            for cell in row.cells
        ]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


# Функция извлекает текст из DOCX, сохраняя порядок абзацев и таблиц.
def extract_text_from_docx(file_path: str) -> list[dict]:
    doc = DocxDocument(file_path)
    blocks = []

    for block in _iter_block_items(doc):
        text = _extract_paragraph_text(block) if isinstance(
            block, Paragraph
        ) else _extract_table_text(block)
        if text:
            blocks.append(text)

    return [{
        "page_start": None,
        "page_end": None,
        "text": "\n\n".join(blocks),
    }]
```

## `core/services/text_cleaning.py`

```python
import re


# Функция очищает извлеченный текст от служебных символов и лишних пробелов.
def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
```

## `core/services/text_chunking.py`

```python
from django.conf import settings
from chonkie import TokenChunker


_token_chunker = None
_token_chunker_config = None


# Функция создает или переиспользует токенизатор с текущими параметрами чанков.
def get_token_chunker():
    global _token_chunker, _token_chunker_config

    config = (settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)

    if _token_chunker is None or _token_chunker_config != config:
        _token_chunker = TokenChunker(
            tokenizer="word",
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        )
        _token_chunker_config = config

    return _token_chunker


# Функция возвращает список текстов чанков без служебной информации.
def split_into_chunks(text: str) -> list[str]:
    chunks = split_into_chunk_objects(text)
    return [chunk.text for chunk in chunks if chunk.text.strip()]


# Функция разбивает полный текст на чанки с учетом размера и перекрытия.
def split_into_chunk_objects(text: str):
    if not text or not text.strip():
        return []
    return get_token_chunker().chunk(text)
```

## `core/services/embeddings.py`

```python
from sentence_transformers import SentenceTransformer


_model = None


# Функция лениво загружает модель эмбеддингов при первом обращении.
def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("intfloat/multilingual-e5-base")
    return _model


# Функция строит эмбеддинг фрагмента документа с префиксом passage:.
def embed_text(text: str) -> list[float]:
    model = get_model()
    return model.encode(
        f"passage: {text}",
        normalize_embeddings=True,
    ).tolist()


# Функция строит эмбеддинг пользовательского вопроса с префиксом query:.
def embed_query(text: str) -> list[float]:
    model = get_model()
    return model.encode(
        f"query: {text}",
        normalize_embeddings=True,
    ).tolist()
```

## `core/services/vector_store.py`

```python
import os
from pathlib import Path
from threading import Lock

import chromadb
from django.conf import settings


# Класс реализует единый persistent-клиент ChromaDB для RAG-поиска.
class ChromaVectorStore:
    _instance = None
    _lock = Lock()

    # Метод создает единственный экземпляр клиента ChromaDB.
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    # Метод инициализирует директорию хранения, клиент и коллекцию ChromaDB.
    def _initialize(self):
        self.chroma_path = os.path.join(settings.BASE_DIR, "chroma_storage")
        os.makedirs(self.chroma_path, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection(
            name="subjects_collection"
        )

    # Метод выполняет векторный поиск фрагментов внутри выбранного предмета.
    def query(self, query_embedding, subject_id, top_k=5):
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"subject_id": str(subject_id)},
            include=["documents", "metadatas", "distances"],
        )

    # Метод переиндексирует в ChromaDB только фрагменты выбранного предмета.
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

            ids, documents, embeddings, metadatas = [], [], [], []
            processed = 0

            for chunk in chunks.iterator(chunk_size=batch_size):
                document = chunk.document
                source_type = Path(document.file.name).suffix.lower().lstrip(".")

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
                    ids, documents, embeddings, metadatas = [], [], [], []

            if ids:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                processed += len(ids)

            return processed

    # Метод удаляет из ChromaDB все фрагменты указанного документа.
    def delete_by_document(self, document_id):
        self.collection.delete(where={"document_id": str(document_id)})
```

## `core/services/document_processor.py`

```python
import os
from time import perf_counter

from core.models import Document, TextChunk
from .embeddings import embed_text
from .text_cleaning import clean_text
from .text_chunking import split_into_chunk_objects
from .text_extraction import TextExtractionError, extract_text
from .vector_store import ChromaVectorStore


# Класс реализует ошибку обработки документа в RAG-конвейере.
class DocumentTextExtractionError(Exception):
    pass


# Функция объединяет извлеченные страницы или блоки в единый очищенный текст.
def _build_document_text(units):
    parts, page_ranges = [], []
    cursor = cleaned_text_length = 0

    for unit in units:
        cleaned_text = clean_text(unit.get("text", ""))
        if not cleaned_text:
            continue

        if parts:
            parts.append("\n\n")
            cursor += 2

        start = cursor
        parts.append(cleaned_text)
        cursor += len(cleaned_text)
        cleaned_text_length += len(cleaned_text)

        page_ranges.append({
            "start": start,
            "end": cursor,
            "page_start": unit.get("page_start"),
            "page_end": unit.get("page_end"),
        })

    return "".join(parts), page_ranges, cleaned_text_length


# Функция определяет номера страниц, к которым относится конкретный чанк.
def _get_chunk_page_range(chunk_start, chunk_end, page_ranges):
    page_starts, page_ends = [], []

    for page_range in page_ranges:
        if chunk_start < page_range["end"] and chunk_end > page_range["start"]:
            if page_range["page_start"] is not None:
                page_starts.append(page_range["page_start"])
            if page_range["page_end"] is not None:
                page_ends.append(page_range["page_end"])

    if not page_starts or not page_ends:
        return None, None
    return min(page_starts), max(page_ends)


# Функция очищает старые фрагменты документа в PostgreSQL и ChromaDB.
def _cleanup_document_index(document, vector_store):
    vector_store.collection.delete(where={"document_id": str(document.id)})
    TextChunk.objects.filter(document=document).delete()


# Функция проверяет совпадение количества чанков в PostgreSQL и ChromaDB.
def _verify_document_index_consistency(document, vector_store):
    postgres_count = TextChunk.objects.filter(document=document).count()
    chroma_chunks = vector_store.collection.get(
        where={"document_id": str(document.id)}
    )
    chroma_count = len(chroma_chunks.get("ids", []))

    if postgres_count != chroma_count:
        _cleanup_document_index(document, vector_store)
        raise DocumentTextExtractionError(
            "Ошибка синхронизации PostgreSQL и ChromaDB"
        )


# Функция формирует метаданные чанка для сохранения в ChromaDB.
def _build_chunk_metadata(chunk, document, file_path):
    metadata = {
        "chunk_id": str(chunk.id),
        "document_id": str(document.id),
        "document_title": str(document.title),
        "subject_id": str(document.subject.id),
        "chunk_index": chunk.chunk_index,
        "source_type": os.path.splitext(file_path)[1][1:],
    }
    if chunk.page_start is not None:
        metadata["page_start"] = chunk.page_start
    if chunk.page_end is not None:
        metadata["page_end"] = chunk.page_end
    return metadata


# Функция выполняет полный цикл обработки документа: извлечение, очистку,
# чанкирование, эмбеддинг, сохранение и проверку согласованности хранилищ.
def process_document(document):
    document = Document.objects.get(id=document.id)
    vector_store = ChromaVectorStore()
    file_path = document.file.path
    started_at = perf_counter()

    _cleanup_document_index(document, vector_store)

    try:
        units = extract_text(file_path)
    except TextExtractionError as exc:
        raise DocumentTextExtractionError(str(exc)) from exc

    document_text, page_ranges, cleaned_text_length = _build_document_text(units)
    chunk_objects = split_into_chunk_objects(document_text)
    created_chunk_count = 0

    for chunk_index, chunk_object in enumerate(chunk_objects):
        chunk_text = clean_text(chunk_object.text)
        if not chunk_text:
            continue

        page_start, page_end = _get_chunk_page_range(
            chunk_object.start_index,
            chunk_object.end_index,
            page_ranges,
        )

        chunk = TextChunk.objects.create(
            document=document,
            content=chunk_text,
            page_start=page_start,
            page_end=page_end,
            chunk_index=chunk_index,
        )

        try:
            vector_store.collection.upsert(
                ids=[str(chunk.id)],
                documents=[chunk.content],
                embeddings=[embed_text(chunk_text)],
                metadatas=[_build_chunk_metadata(chunk, document, file_path)],
            )
        except Exception as exc:
            _cleanup_document_index(document, vector_store)
            raise DocumentTextExtractionError(
                "Не удалось сохранить фрагменты документа в ChromaDB"
            ) from exc

        created_chunk_count += 1

    if created_chunk_count == 0:
        raise DocumentTextExtractionError("Не удалось извлечь текст")

    _verify_document_index_consistency(document, vector_store)
```

## `core/services/retriever.py`

```python
from chromadb.errors import InternalError
from django.conf import settings

from core.models import Document
from .embeddings import embed_query
from .vector_store import ChromaVectorStore


# Функция дополняет метаданные названием документа, если оно отсутствует.
def _fill_document_titles(metadatas):
    missing_ids = [
        str(meta.get("document_id"))
        for meta in metadatas
        if meta.get("document_id") and not meta.get("document_title")
    ]
    documents_by_id = {
        str(document.id): document.title
        for document in Document.objects.filter(id__in=missing_ids).only("id", "title")
    }

    for meta in metadatas:
        if not meta.get("document_title") and meta.get("document_id"):
            meta["document_title"] = documents_by_id.get(str(meta["document_id"]))

    return metadatas


# Функция ищет релевантные чанки и отбрасывает результаты выше порога расстояния.
def retrieve_chunks(question, subject, top_k=5):
    vector_store = ChromaVectorStore()
    question_embedding = embed_query(question)

    try:
        results = vector_store.query(question_embedding, str(subject.id), top_k)
    except InternalError:
        vector_store.rebuild_subject_from_postgres(subject.id)
        results = vector_store.query(question_embedding, str(subject.id), top_k)

    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    distances = results.get("distances", [])

    if documents and isinstance(documents[0], list):
        documents = documents[0]
    if metadatas and isinstance(metadatas[0], list):
        metadatas = metadatas[0]
    if distances and isinstance(distances[0], list):
        distances = distances[0]

    filtered_documents, filtered_metadatas = [], []
    threshold = settings.RAG_RELEVANCE_DISTANCE_THRESHOLD

    for index, document in enumerate(documents):
        metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None

        if distance is not None:
            metadata["distance"] = distance

        if distance is None or distance <= threshold:
            filtered_documents.append(document)
            filtered_metadatas.append(metadata)

    return filtered_documents, _fill_document_titles(filtered_metadatas)


# Функция преобразует метаданные найденных чанков в список уникальных источников.
def normalize_sources(metadatas):
    unique_sources, seen = [], set()

    for meta in _fill_document_titles(metadatas):
        key = (meta.get("document_id"), meta.get("page_start"), meta.get("page_end"))

        if key not in seen and meta.get("document_title"):
            seen.add(key)
            unique_sources.append({
                "document_id": meta.get("document_id"),
                "document_title": meta.get("document_title"),
                "page_start": meta.get("page_start"),
                "page_end": meta.get("page_end"),
                "chunk_id": meta.get("chunk_id"),
            })

    return unique_sources
```

## `core/services/prompt_builder.py`

```python
NO_RELEVANT_INFO_ANSWER = "В предоставленных документах нет информации об этом"


# Функция формирует промт для языковой модели на основе найденных фрагментов.
def build_prompt(documents, metadatas, question):
    if not documents:
        return NO_RELEVANT_INFO_ANSWER

    chunks = []

    for doc, meta in zip(documents, metadatas):
        title = meta.get("document_title")
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")

        if page_start and page_end and page_start != page_end:
            page_info = f"стр. {page_start}-{page_end}"
        elif page_start:
            page_info = f"стр. {page_start}"
        else:
            page_info = ""

        chunks.append(
            f"{'Источник: ' + title + chr(10) if title else ''}"
            f"{page_info + chr(10) if page_info else ''}"
            f"Текст:\n{doc}"
        )

    context = "\n\n---\n\n".join(chunks)

    return f"""
Ты — система ответов строго по предоставленным документам.

Правила:
1. Отвечай только на основании материалов ниже.
2. Не используй внешние знания, предположения и примерные расчеты.
3. Не придумывай исходные данные, числа, даты, цены, названия и факты.
4. Если в материалах нет прямого ответа на вопрос, ответь ровно так:
{NO_RELEVANT_INFO_ANSWER}
5. Если ответа нет, не объясняй возможные причины и не предлагай расчет.
6. Не указывай источники в тексте ответа: приложение добавит их отдельно.

Материалы:
{context}

Вопрос:
{question}
"""
```

## `core/services/gigachat_client.py`

```python
from threading import Lock
from gigachat import GigaChat
from django.conf import settings


gigachat_lock = Lock()


# Функция создает клиент GigaChat с настройками авторизации проекта.
def get_gigachat_client():
    return GigaChat(
        credentials=settings.GIGACHAT_CREDENTIALS,
        scope="GIGACHAT_API_PERS",
        verify_ssl_certs=False,
    )


# Функция отправляет сформированный промт в GigaChat и возвращает текст ответа.
def ask_gigachat(prompt: str) -> str:
    with gigachat_lock:
        giga = get_gigachat_client()
        response = giga.chat(prompt)
        return response.choices[0].message.content
```

## `core/services/rag_pipeline.py`

```python
from core.services.gigachat_client import ask_gigachat
from core.services.prompt_builder import build_prompt
from core.services.retriever import normalize_sources, retrieve_chunks


NO_RELEVANT_INFO_ANSWER = "В предоставленных документах нет информации об этом"


# Функция проверяет, что ответ модели сообщает об отсутствии информации.
def _is_no_relevant_info_answer(answer):
    if not answer:
        return False

    normalized_answer = answer.lower().replace("ё", "е")
    return (
        NO_RELEVANT_INFO_ANSWER.lower().replace("ё", "е") in normalized_answer
        or "нет информации" in normalized_answer
        or "отсутствует информация" in normalized_answer
    )


# Функция реализует общий RAG-сценарий ответа на вопрос пользователя.
def answer_question(question, subject, top_k=5):
    documents, metadatas = retrieve_chunks(
        question=question,
        subject=subject,
        top_k=top_k,
    )

    if not documents:
        return {
            "answer": NO_RELEVANT_INFO_ANSWER,
            "sources": [],
            "metadatas": metadatas,
        }

    prompt = build_prompt(documents, metadatas, question)
    answer = ask_gigachat(prompt)
    sources = normalize_sources(metadatas)

    if _is_no_relevant_info_answer(answer):
        sources = []

    return {
        "answer": answer,
        "sources": sources,
        "metadatas": metadatas,
    }
```

## `core/views.py`

```python
SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx"}


# Функция удаляет документ и связанные с ним чанки из PostgreSQL и ChromaDB.
@login_required
def delete_document(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)

    if document.subject.teacher.user != request.user:
        return HttpResponseForbidden("Нет доступа")

    subject_id = document.subject.id
    vector_store = ChromaVectorStore()

    # При удалении документа связанные фрагменты удаляются
    # из векторного хранилища и из реляционной базы данных.
    vector_store.collection.delete(where={"document_id": str(document.id)})
    TextChunk.objects.filter(document=document).delete()

    document.file.delete(save=False)
    document.delete()

    return redirect("subject_materials", subject_id=subject_id)


# Функция обрабатывает страницу материалов предмета и запуск индексации документа.
@login_required
def subject_materials(request, subject_id):
    teacher = TeacherProfile.objects.get(user=request.user)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    upload_error = None

    if request.method == "POST":
        file = request.FILES.get("file")

        if file:
            file_extension = Path(file.name).suffix.lower()
            if file_extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
                upload_error = (
                    "Неподдерживаемый формат файла. "
                    "Можно загрузить PDF или Word (.docx)."
                )
            else:
                document = Document.objects.create(
                    title=file.name,
                    file=file,
                    subject=subject,
                )

                try:
                    process_document(document)
                except DocumentTextExtractionError as exc:
                    document.file.delete(save=False)
                    document.delete()
                    upload_error = str(exc) or "Не удалось извлечь текст из файла."
                else:
                    return redirect("subject_materials", subject_id=subject.id)

        if not file:
            upload_error = "Выберите файл для загрузки."

    documents = subject.documents.all().order_by("-uploaded_at")
    return render(request, "core/subject_materials.html", {
        "subject": subject,
        "documents": documents,
        "upload_error": upload_error,
    })


# Функция принимает вопрос студента, запускает RAG-конвейер и сохраняет ответ.
@login_required
@require_http_methods(["POST"])
def send_message(request, subject_id):
    student = StudentProfile.objects.get(user=request.user)
    subject = get_object_or_404(Subject, id=subject_id, students=student)
    question = json.loads(request.body).get("question", "").strip()

    if not question:
        return JsonResponse({"error": "Введите вопрос"}, status=400)

    question_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=question,
        is_question=True,
    )

    try:
        rag_result = answer_question(question=question, subject=subject)
        answer_text = _append_sources_to_answer(
            rag_result["answer"],
            rag_result["sources"],
        )
        answer_sources = rag_result["sources"]
    except Exception:
        answer_text = "Произошла ошибка при обработке запроса."
        answer_sources = []

    answer_msg = ChatMessage.objects.create(
        student=student,
        subject=subject,
        message=answer_text,
        is_question=False,
        sources=answer_sources,
    )

    return JsonResponse({
        "success": True,
        "question": {"id": question_msg.id, "message": question_msg.message},
        "answer": {
            "id": answer_msg.id,
            "message": answer_msg.message,
            "sources": answer_msg.sources or [],
        },
    })
```
