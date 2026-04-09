from .embeddings import embed_text
from .vector_store import ChromaVectorStore


def retrieve_chunks(question, subject, top_k=5):
    vector_store = ChromaVectorStore()
    question_embedding = embed_text(question)

    results = vector_store.query(
        query_embedding=question_embedding,
        subject_id=str(subject.id),
        top_k=top_k,
    )
    print("RESULTS ", results)

    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])

    if documents and isinstance(documents[0], list):
        documents = documents[0]
    if metadatas and isinstance(metadatas[0], list):
        metadatas = metadatas[0]

    return documents, metadatas
