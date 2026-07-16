from django.conf import settings
from chonkie import TokenChunker


_token_chunker = None
_token_chunker_config = None


def get_token_chunker():
    global _token_chunker, _token_chunker_config

    config = (
        settings.RAG_CHUNK_SIZE,
        settings.RAG_CHUNK_OVERLAP,
    )

    if _token_chunker is None or _token_chunker_config != config:
        _token_chunker = TokenChunker(
            tokenizer="word",
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        )
        _token_chunker_config = config

    return _token_chunker


def split_into_chunks(text: str) -> list[str]:
    chunks = split_into_chunk_objects(text)

    return [chunk.text for chunk in chunks if chunk.text.strip()]


def split_into_chunk_objects(text: str):
    if not text or not text.strip():
        return []

    return get_token_chunker().chunk(text)
