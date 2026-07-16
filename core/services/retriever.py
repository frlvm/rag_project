import logging

from chromadb.errors import InternalError
from django.conf import settings

from core.models import Document

from .embeddings import embed_query
from .logging_utils import log_event
from .vector_store import ChromaVectorStore


logger = logging.getLogger("core.rag")


def _fill_document_titles(metadatas):
    missing_ids = []

    for meta in metadatas:
        if meta.get("document_title"):
            continue

        document_id = meta.get("document_id")
        if document_id:
            missing_ids.append(str(document_id))

    if not missing_ids:
        return metadatas

    documents_by_id = {
        str(document.id): document.title
        for document in Document.objects.filter(id__in=missing_ids).only("id", "title")
    }

    for meta in metadatas:
        if meta.get("document_title"):
            continue

        document_id = meta.get("document_id")
        if document_id:
            meta["document_title"] = documents_by_id.get(str(document_id))

    return metadatas


def _query_subject_chunks(vector_store, question_embedding, subject, top_k):
    return vector_store.query(
        query_embedding=question_embedding,
        subject_id=str(subject.id),
        top_k=top_k
    )


def retrieve_chunks(question, subject, top_k=5):
    vector_store = ChromaVectorStore()

    question_embedding = embed_query(question)

    try:
        results = _query_subject_chunks(vector_store, question_embedding, subject, top_k)
    except InternalError as exc:
        log_event(
            logger,
            logging.ERROR,
            "chroma_query_failed_subject_rebuild_started",
            subject_id=subject.id,
            top_k=top_k,
            question_length=len(question),
            error=str(exc),
        )
        restored_chunk_count = vector_store.rebuild_subject_from_postgres(subject.id)
        log_event(
            logger,
            logging.WARNING,
            "chroma_query_retry_after_subject_rebuild",
            subject_id=subject.id,
            top_k=top_k,
            question_length=len(question),
            restored_chunk_count=restored_chunk_count,
        )
        results = _query_subject_chunks(vector_store, question_embedding, subject, top_k)
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    distances = results.get("distances", [])

    if documents and isinstance(documents[0], list):
        documents = documents[0]
    if metadatas and isinstance(metadatas[0], list):
        metadatas = metadatas[0]
    if distances and isinstance(distances[0], list):
        distances = distances[0]

    distance_threshold = settings.RAG_RELEVANCE_DISTANCE_THRESHOLD
    raw_results_count = len(documents)
    filtered_documents = []
    filtered_metadatas = []

    for index, document in enumerate(documents):
        metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None

        if distance is not None:
            metadata["distance"] = distance

        if distance is None or distance <= distance_threshold:
            filtered_documents.append(document)
            filtered_metadatas.append(metadata)

    documents = filtered_documents
    metadatas = _fill_document_titles(filtered_metadatas)

    log_event(
        logger,
        logging.INFO,
        "retrieval_finished",
        subject_id=subject.id,
        top_k=top_k,
        question_length=len(question),
        raw_results_count=raw_results_count,
        results_count=len(documents),
        filtered_out_count=raw_results_count - len(documents),
        distance_threshold=distance_threshold,
        min_distance=min(distances) if distances else None,
    )

    return documents, metadatas


def normalize_sources(metadatas):
    metadatas = _fill_document_titles(metadatas)
    unique_sources = []
    seen = set()

    for meta in metadatas:
        document_id = meta.get("document_id")
        document_title = meta.get("document_title")
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")
        chunk_id = meta.get("chunk_id")

        key = (document_id, page_start, page_end)

        if key not in seen and document_title:
            seen.add(key)
            unique_sources.append({
                "document_id": document_id,
                "document_title": document_title,
                "page_start": page_start,
                "page_end": page_end,
                "chunk_id": chunk_id,
            })

    return unique_sources
