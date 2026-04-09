import os
import fitz  # PyMuPDF
from docx import Document as DocxDocument
from docx2pdf import convert
from PyPDF2 import PdfReader
import tempfile
import os


def extract_text(file_path: str) -> list[dict]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    else:
        raise ValueError("Неподдерживаемый формат файла")


def extract_text_from_pdf(file_path: str) -> list[dict]:
    units=[]
    with fitz.open(file_path) as pdf:
        for i, page in enumerate(pdf, start=1):
            units.append({
                "page_start": i,
                "page_end": i,
                "text": page.get_text()
            })

    return units


def extract_text_from_docx(file_path: str) -> list[dict]:
    doc = DocxDocument(file_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    return [{
        "page_start": None,
        "page_end": None,
        "text": text
        }]