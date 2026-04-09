import os

from core.models import Document, TextChunk

from .embeddings import embed_text
from .text_chunking import split_into_chunks
from .text_cleaning import clean_text
from .text_extraction import extract_text
from .vector_store import ChromaVectorStore


def process_document(document):
    document = Document.objects.get(id=document.id)
    vector_store = ChromaVectorStore()

    vector_store.delete_by_document(document.id)
    TextChunk.objects.filter(document=document).delete()

    file_path = document.file.path
    units = extract_text(file_path)
    global_chunk_index = 0

    for unit in units:
        raw_text = unit.get("text", "")
        page_start = unit.get("page_start")
        page_end = unit.get("page_end")

        cleaned_text = clean_text(raw_text)
        chunks = split_into_chunks(cleaned_text)

        for chunk_text in chunks:
            chunk = TextChunk.objects.create(
                document=document,
                content=chunk_text,
                page_start=page_start,
                page_end=page_end,
                chunk_index=global_chunk_index,
            )

            embedding = embed_text(chunk_text)
            metadata = {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_title": document.title,
                "subject_id": str(document.subject.id),
                "chunk_index": chunk.chunk_index,
                "source_type": os.path.splitext(file_path)[1][1:],
            }

            if chunk.page_start is not None:
                metadata["page_start"] = chunk.page_start

            if chunk.page_end is not None:
                metadata["page_end"] = chunk.page_end

            vector_store.collection.upsert(
                ids=[str(chunk.id)],
                documents=[chunk.content],
                embeddings=[embedding],
                metadatas=[metadata],
            )

            global_chunk_index += 1
