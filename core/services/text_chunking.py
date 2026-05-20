from chonkie import TokenChunker

# создаём один раз — лучше на уровне модуля
token_chunker = TokenChunker(
    tokenizer="word",
    chunk_size=500,
    chunk_overlap=100
)

def split_into_chunks(text: str) -> list[str]:
    if not text or not text.strip():
        return []

    chunks = token_chunker.chunk(text)

    # возвращаем текст чанков
    return [chunk.text for chunk in chunks if chunk.text.strip()]
