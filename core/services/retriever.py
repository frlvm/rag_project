from .vector_store import ChromaVectorStore
from .embeddings import embed_text



def retrieve_chunks(question, subject, top_k=5):
    vector_store = ChromaVectorStore()

    question_embedding = embed_text(question)

    results = vector_store.query(
        query_embedding=question_embedding,
        subject_id=subject.id,
        top_k=top_k
    )

    return results["documents"][0]
