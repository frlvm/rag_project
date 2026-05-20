import logging

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


def retrieve_chunks(question, subject, top_k=5):
    vector_store = ChromaVectorStore()

    question_embedding = embed_query(question)

    results = vector_store.query(
        query_embedding=question_embedding,
        subject_id=str(subject.id),
        top_k=top_k
    )
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])

    # нормализация
    if documents and isinstance(documents[0], list):
        documents = documents[0]
    if metadatas and isinstance(metadatas[0], list):
        metadatas = metadatas[0]

    metadatas = _fill_document_titles(metadatas)

    log_event(
        logger,
        logging.INFO,
        "retrieval_finished",
        subject_id=subject.id,
        top_k=top_k,
        question_length=len(question),
        results_count=len(documents),
    )

    return documents, metadatas


def normalize_sources(metadatas):
    """
    Превращает metadatas из ChromaDB в удобный список источников без дублей.
    """
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
