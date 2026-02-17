from .text_extraction import extract_text
from .text_cleaning import clean_text
from .text_chunking import split_into_chunks
from .embeddings import embed_text
from core.models import TextChunk
from .vector_store import ChromaVectorStore
import uuid



def process_document(document):
    vector_store = ChromaVectorStore()
    
    content = extract_text(document.file.path)
    content = clean_text(content)
    chunks = split_into_chunks(content)

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for chunk in chunks:
        # сохраняем текст chunk в PostgreSQL
        text_chunk = TextChunk.objects.create(
            document=document,
            content=chunk
        )

        ids.append(str(text_chunk.id))
        documents.append(chunk)
        embeddings.append(embed_text(chunk))
        metadatas.append({
            "subject_id": document.subject.id,
            "document_id": document.id
        })

    # добавляем в Chroma одним батчем
    vector_store.add_documents(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )
