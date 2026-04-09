import os
from .text_extraction import extract_text
from .text_cleaning import clean_text
from .text_chunking import split_into_chunks
from .embeddings import embed_text
from core.models import TextChunk, Document
from .vector_store import ChromaVectorStore
from pypdf import PdfReader

def extract_pdf_pages(file_path: str):

    reader = PdfReader(file_path)
    pages = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append({
                "page_number": index,
                "text": text
            })

    return pages

def process_document(document):
    document = Document.objects.get(id=document.id)
    vector_store = ChromaVectorStore()

    # 🔥 1. УДАЛЯЕМ старые чанки ТОЛЬКО этого документа
    vector_store.collection.delete(
        where={"document_id": str(document.id)}
    )

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
                chunk_index=global_chunk_index
            )

            embedding = embed_text(chunk_text)

            metadata = {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "subject_id": str(document.subject.id),
                "chunk_index": chunk.chunk_index,
                "source_type": os.path.splitext(file_path)[1][1:],  # pdf/docx
            }

            if chunk.page_start is not None:
                metadata["page_start"] = chunk.page_start

            if chunk.page_end is not None:
                metadata["page_end"] = chunk.page_end

            vector_store.collection.upsert(
                ids=[str(chunk.id)],
                documents=[chunk.content],
                embeddings=[embedding],
                metadatas=[metadata]
            )

            global_chunk_index += 1

'''
def process_document(document):
    document = Document.objects.get(id=document.id)
    vector_store = ChromaVectorStore()
    # Удаляем старые чанки из Chroma по subject_id + document_title
    try:
        vector_store.delete_by_document(document.title)
    except Exception as e:
        print(f"Ошибка при удалении чанков из Chroma: {e}")

    # Удаляем старые чанки из БД
    TextChunk.objects.filter(
        document__title=document.title
    ).delete()

    vector_store.collection.delete(
    where={"document_id": str(document.id)}
    )

    file_path = document.file.path
    units = extract_text(file_path)

    created_chunk_ids = []
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
                chunk_index=global_chunk_index
            )

            created_chunk_ids.append(str(chunk.id))

            embedding = embed_text(chunk_text)

            metadata = {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_title": str(document.title),
                "subject_id": str(document.subject.id),
                "chunk_index": chunk.chunk_index,
            }

            if chunk.page_start is not None:
                metadata["page_start"] = chunk.page_start

            if chunk.page_end is not None:
                metadata["page_end"] = chunk.page_end

            vector_store.collection.upsert(
                ids=[str(chunk.id)],
                documents=[chunk.content],
                embeddings=[embedding],
                metadatas=[metadata]
            )

            print("ADDED CHUNK:", metadata)

            global_chunk_index += 1

    if created_chunk_ids:
        stored = vector_store.collection.get(
            ids=[created_chunk_ids[-1]],
            include=["metadatas", "documents"]
        )
        print("STORED IN CHROMA:", stored)
'''