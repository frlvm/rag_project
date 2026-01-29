from .text_extraction import extract_text
from .text_cleaning import clean_text
from .text_chunking import split_into_chunks
from .embeddings import embed_text
from core.models import TextChunk

def process_document(document):
    content = extract_text(document.file.path)
    content = clean_text(content)
    chunks = split_into_chunks(content)

    for chunk in chunks:
        TextChunk.objects.create(
            document=document,
            content=chunk,
            embedding=embed_text(chunk)
        )
