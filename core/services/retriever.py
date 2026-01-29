import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from core.models import TextChunk


def retrieve_chunks(question_embedding, subject, top_k=5):
    chunks = TextChunk.objects.filter(
        document__subject=subject
    )

    embeddings = []
    texts = []

    for chunk in chunks:
        embeddings.append(chunk.embedding)
        texts.append(chunk.content)

    similarities = cosine_similarity(
        [question_embedding],
        embeddings
    )[0]

    top_indices = np.argsort(similarities)[-top_k:][::-1]

    return [texts[i] for i in top_indices]
