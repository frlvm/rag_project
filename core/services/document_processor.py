import logging
import os
from time import perf_counter

from core.models import Document, TextChunk

from .embeddings import embed_text
from .logging_utils import log_event, print_document_upload_event
from .text_cleaning import clean_text
from .text_chunking import split_into_chunk_objects
from .text_extraction import TextExtractionError, extract_text
from .vector_store import ChromaVectorStore


logger = logging.getLogger("core.rag")


class DocumentTextExtractionError(Exception):
    pass


def _build_document_text(units):
    parts = []
    page_ranges = []
    cursor = 0
    cleaned_text_length = 0

    for unit in units:
        cleaned_text = clean_text(unit.get("text", ""))
        if not cleaned_text:
            continue

        if parts:
            separator = "\n\n"
            parts.append(separator)
            cursor += len(separator)

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


def _get_chunk_page_range(chunk_start, chunk_end, page_ranges):
    page_starts = []
    page_ends = []

    for page_range in page_ranges:
        if chunk_start < page_range["end"] and chunk_end > page_range["start"]:
            if page_range["page_start"] is not None:
                page_starts.append(page_range["page_start"])
            if page_range["page_end"] is not None:
                page_ends.append(page_range["page_end"])

    if not page_starts or not page_ends:
        return None, None

    return min(page_starts), max(page_ends)


def _cleanup_document_index(document, vector_store):
    vector_store.collection.delete(where={"document_id": str(document.id)})
    TextChunk.objects.filter(document=document).delete()


def _get_chroma_chunk_count(document, vector_store):
    chroma_chunks = vector_store.collection.get(
        where={"document_id": str(document.id)}
    )
    return len(chroma_chunks.get("ids", []))


def _verify_document_index_consistency(document, vector_store):
    postgres_count = TextChunk.objects.filter(document=document).count()
    chroma_count = _get_chroma_chunk_count(document, vector_store)

    if postgres_count == chroma_count:
        log_event(
            logger,
            logging.INFO,
            "document_index_consistency_verified",
            document_id=document.id,
            subject_id=document.subject.id,
            postgres_chunk_count=postgres_count,
            chroma_chunk_count=chroma_count,
        )
        return

    log_event(
        logger,
        logging.ERROR,
        "document_index_consistency_failed",
        document_id=document.id,
        subject_id=document.subject.id,
        postgres_chunk_count=postgres_count,
        chroma_chunk_count=chroma_count,
    )
    _cleanup_document_index(document, vector_store)
    raise DocumentTextExtractionError(
        "Ошибка синхронизации PostgreSQL и ChromaDB"
    )


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

    _cleanup_document_index(document, vector_store)

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

    document_text, page_ranges, cleaned_text_length = _build_document_text(units)
    chunk_objects = split_into_chunk_objects(document_text)

    first_chunk = None
    last_chunk = None
    created_chunk_count = 0

    for global_chunk_index, chunk_object in enumerate(chunk_objects):
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
            chunk_index=global_chunk_index,
        )
        if first_chunk is None:
            first_chunk = chunk
        last_chunk = chunk

        try:
            embedding = embed_text(chunk_text)
            metadata = _build_chunk_metadata(chunk, document, file_path)
            vector_store.collection.upsert(
                ids=[str(chunk.id)],
                documents=[chunk.content],
                embeddings=[embedding],
                metadatas=[metadata],
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "document_index_write_failed",
                document_id=document.id,
                subject_id=document.subject.id,
                chunk_id=chunk.id,
                error=str(exc),
            )
            _cleanup_document_index(document, vector_store)
            raise DocumentTextExtractionError(
                "Не удалось сохранить фрагменты документа в ChromaDB"
            ) from exc

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

    _verify_document_index_consistency(document, vector_store)

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
