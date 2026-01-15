import os
import fitz  # PyMuPDF
from docx import Document as DocxDocument


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    else:
        raise ValueError("Неподдерживаемый формат файла")


def extract_text_from_pdf(file_path: str) -> str:
    text = []

    with fitz.open(file_path) as pdf:
        for page in pdf:
            text.append(page.get_text())

    return "\n".join(text)


def extract_text_from_docx(file_path: str) -> str:
    doc = DocxDocument(file_path)
    return "\n".join(p.text for p in doc.paragraphs)
