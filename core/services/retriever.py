from .vector_store import ChromaVectorStore
from .embeddings import embed_text



def retrieve_chunks(question, subject, top_k=5):
    vector_store = ChromaVectorStore()

    question_embedding = embed_text(question)

    results = vector_store.query(
        query_embedding=question_embedding,
        subject_id=str(subject.id),
        top_k=top_k
    )
    print("RESULTS ", results)
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])

    # нормализация
    if documents and isinstance(documents[0], list):
        documents = documents[0]
    if metadatas and isinstance(metadatas[0], list):
        metadatas = metadatas[0]

    return documents, metadatas


def normalize_sources(metadatas):
    """
    Превращает metadatas из ChromaDB в удобный список источников без дублей.
    """
    unique_sources = []
    seen = set()

    for meta in metadatas:
        document_id = meta.get("document_id")
        document_title = meta.get("document_title")
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")
        chunk_id = meta.get("chunk_id")

        key = (document_id, page_start, page_end)

        if key not in seen:
            seen.add(key)
            unique_sources.append({
                "document_id": document_id,
                "document_title": document_title,
                "page_start": page_start,
                "page_end": page_end,
                "chunk_id": chunk_id,
            })

    return unique_sources