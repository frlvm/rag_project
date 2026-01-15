from core.services.embeddings import embed_text
from core.models import TextChunk

def process_document(document, chunks: list[str]):
    for text in chunks:
        embedding = embed_text(text)

        TextChunk.objects.create(
            document=document,
            content=text,
            embedding=embedding
        )
