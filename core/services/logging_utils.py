import json
import logging
from contextlib import contextmanager
from time import perf_counter


logger = logging.getLogger("core.rag")


def _serialize_fields(fields):
    return json.dumps(fields, ensure_ascii=False, default=str, sort_keys=True)


def log_event(logger, level, event, **fields):
    logger.log(level, "%s | %s", event, _serialize_fields(fields))


def _short_text(value, limit=140):
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def log_document_upload_event(
    document,
    first_chunk,
    last_chunk,
    chunk_count,
    unit_count,
    duration_ms,
):
    subject = document.subject
    teacher = subject.teacher
    file_size = document.file.size if document.file else 0

    log_event(
        logger,
        logging.INFO,
        "document_upload_summary",
        document_id=document.id,
        document_title=document.title,
        file_size=file_size,
        subject_id=subject.id,
        subject_name=subject.name,
        teacher_id=teacher.id,
        unit_count=unit_count,
        chunk_count=chunk_count,
        first_chunk_id=first_chunk.id if first_chunk else None,
        first_chunk_index=first_chunk.chunk_index if first_chunk else None,
        first_chunk_preview=_short_text(first_chunk.content) if first_chunk else None,
        last_chunk_id=last_chunk.id if last_chunk else None,
        last_chunk_index=last_chunk.chunk_index if last_chunk else None,
        last_chunk_preview=_short_text(last_chunk.content) if last_chunk else None,
        duration_ms=duration_ms,
    )


def log_document_delete_event(
    document_data,
    postgresql_found_ids,
    postgresql_deleted_ids,
    chroma_found_ids,
    chroma_deleted_ids,
    chroma_remaining_ids,
    duration_ms,
):
    log_event(
        logger,
        logging.INFO,
        "document_delete_summary",
        **document_data,
        postgresql_found_ids=postgresql_found_ids,
        postgresql_deleted_ids=postgresql_deleted_ids,
        chroma_found_ids=chroma_found_ids,
        chroma_deleted_ids=chroma_deleted_ids,
        chroma_remaining_ids=chroma_remaining_ids,
        duration_ms=duration_ms,
    )


def log_rag_question_event(
    subject,
    question,
    metadatas,
    answer,
    duration_ms,
    documents=None,
):
    documents = documents or []
    teacher = subject.teacher
    chunk_ids = [
        meta.get("chunk_id")
        for meta in metadatas
        if meta.get("chunk_id")
    ]
    document_titles = sorted({
        str(meta.get("document_title"))
        for meta in metadatas
        if meta.get("document_title")
    })
    subject_ids = sorted({
        str(meta.get("subject_id"))
        for meta in metadatas
        if meta.get("subject_id")
    })

    log_event(
        logger,
        logging.INFO,
        "rag_question_summary",
        subject_id=subject.id,
        subject_name=subject.name,
        teacher_id=teacher.id,
        question_length=len(question) if question else 0,
        question_preview=_short_text(question, limit=180),
        chunk_count=len(metadatas),
        chunk_ids=chunk_ids,
        document_titles=document_titles,
        metadata_subject_ids=subject_ids,
        retrieved_document_count=len(documents),
        answer_length=len(answer) if answer else 0,
        answer_preview=_short_text(answer, limit=180),
        duration_ms=duration_ms,
    )


@contextmanager
def log_timed_event(logger, level, event, **fields):
    started_at = perf_counter()
    log_event(logger, level, f"{event}_started", **fields)

    try:
        yield
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        log_event(
            logger,
            logging.ERROR,
            f"{event}_failed",
            duration_ms=duration_ms,
            **fields,
        )
        logger.exception("%s_exception", event)
        raise
    else:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        log_event(
            logger,
            level,
            f"{event}_finished",
            duration_ms=duration_ms,
            **fields,
        )
