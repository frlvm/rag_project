import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from core.models import TextChunk
from core.services.embeddings import embed_text

def retrieve_chunks(question, top_k=5):
    query_vec = np.array(embed_text(question)).reshape(1, -1)

    chunks = TextChunk.objects.exclude(embedding=None)
    if not chunks.exists():
        return []

    vectors = np.array([c.embedding for c in chunks])
    similarities = cosine_similarity(query_vec, vectors)[0]

    ranked = sorted(
        zip(chunks, similarities),
        key=lambda x: x[1],
        reverse=True
    )

    return [chunk for chunk, _ in ranked[:top_k]]
