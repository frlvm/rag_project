import os
import logging
from time import perf_counter
from .text_extraction import TextExtractionError, extract_text
from .text_cleaning import clean_text
from .text_chunking import split_into_chunks
from .embeddings import embed_text
from core.models import TextChunk, Document
from .vector_store import ChromaVectorStore
from pypdf import PdfReader
from .logging_utils import log_event, print_document_upload_event


logger = logging.getLogger("core.rag")


class DocumentTextExtractionError(Exception):
    pass


def extract_pdf_pages(file_path: str):

    reader = PdfReader(file_path)
    pages = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append({
                "page_number": index,
                "text": text
            })

    return pages

def process_document(document):
    document = Document.objects.get(id=document.id)
    vector_store = ChromaVectorStore()
    file_path = document.file.path
    processing_started_at = perf_counter()

    log_event(
        logger,
        logging.INFO,
        "document_processing_started",
        document_id=document.id,
        subject_id=document.subject.id,
        document_title=document.title,
        file_path=file_path,
    )

    # 🔥 1. УДАЛЯЕМ старые чанки ТОЛЬКО этого документа
    vector_store.collection.delete(
        where={"document_id": str(document.id)}
    )

    TextChunk.objects.filter(document=document).delete()

    extract_started_at = perf_counter()
    try:
        units = extract_text(file_path)
    except TextExtractionError as exc:
        raise DocumentTextExtractionError(str(exc)) from exc

    log_event(
        logger,
        logging.INFO,
        "document_text_extracted",
        document_id=document.id,
        subject_id=document.subject.id,
        unit_count=len(units),
        duration_ms=round((perf_counter() - extract_started_at) * 1000, 2),
    )

    global_chunk_index = 0
    created_chunk_count = 0
    first_chunk = None
    last_chunk = None
    cleaned_text_length = 0

    for unit in units:
        raw_text = unit.get("text", "")
        page_start = unit.get("page_start")
        page_end = unit.get("page_end")

        cleaned_text = clean_text(raw_text)
        if cleaned_text:
            cleaned_text_length += len(cleaned_text)
        else:
            continue

        chunks = split_into_chunks(cleaned_text)

        for chunk_text in chunks:
            chunk_text = clean_text(chunk_text)
            if not chunk_text:
                continue

            chunk = TextChunk.objects.create(
                document=document,
                content=chunk_text,
                page_start=page_start,
                page_end=page_end,
                chunk_index=global_chunk_index
            )
            if first_chunk is None:
                first_chunk = chunk
            last_chunk = chunk

            embedding = embed_text(chunk_text)

            metadata = {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_title": str(document.title),
                "subject_id": str(document.subject.id),
                "chunk_index": chunk.chunk_index,
                "source_type": os.path.splitext(file_path)[1][1:],  # pdf/docx
            }

            if chunk.page_start is not None:
                metadata["page_start"] = chunk.page_start

            if chunk.page_end is not None:
                metadata["page_end"] = chunk.page_end

            vector_store.collection.upsert(
                ids=[str(chunk.id)],
                documents=[chunk.content],
                embeddings=[embedding],
                metadatas=[metadata]
            )

            global_chunk_index += 1
            created_chunk_count += 1

            log_event(
                logger,
                logging.INFO,
                "chunk_upserted",
                document_id=document.id,
                subject_id=document.subject.id,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                source_type=metadata["source_type"],
            )

    if created_chunk_count == 0:
        log_event(
            logger,
            logging.WARNING,
            "document_text_extraction_empty",
            document_id=document.id,
            subject_id=document.subject.id,
            document_title=document.title,
            unit_count=len(units),
            cleaned_text_length=cleaned_text_length,
        )
        raise DocumentTextExtractionError("Не удалось извлечь текст")

    log_event(
        logger,
        logging.INFO,
        "document_text_cleaned",
        document_id=document.id,
        subject_id=document.subject.id,
        document_title=document.title,
        cleaned_text_length=cleaned_text_length,
    )

    duration_ms = round((perf_counter() - processing_started_at) * 1000, 2)

    log_event(
        logger,
        logging.INFO,
        "document_processing_finished",
        document_id=document.id,
        subject_id=document.subject.id,
        document_title=document.title,
        unit_count=len(units),
        chunk_count=created_chunk_count,
        duration_ms=duration_ms,
    )

    print_document_upload_event(
        document=document,
        first_chunk=first_chunk,
        last_chunk=last_chunk,
        chunk_count=created_chunk_count,
        unit_count=len(units),
        duration_ms=duration_ms,
    )
