from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("intfloat/multilingual-e5-base")
    return _model


def embed_text(text: str) -> list[float]:
    model = get_model()
    return model.encode(
        f"passage: {text}",
        normalize_embeddings=True
    ).tolist()


def embed_query(text: str) -> list[float]:
    model = get_model()
    return model.encode(
        f"query: {text}",
        normalize_embeddings=True
    ).tolist()