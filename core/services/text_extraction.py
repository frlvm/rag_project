import os

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from docx.document import Document as DocxDocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


class TextExtractionError(Exception):
    pass


def extract_text(file_path: str) -> list[dict]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    if ext == ".docx":
        return extract_text_from_docx(file_path)
    if ext == ".txt":
        return extract_text_from_txt(file_path)

    raise ValueError("Неподдерживаемый формат файла")


def extract_text_from_pdf(file_path: str) -> list[dict]:
    units = []
    with fitz.open(file_path) as pdf:
        for i, page in enumerate(pdf, start=1):
            text = page.get_text()
            units.append({
                "page_start": i,
                "page_end": i,
                "text": text
            })

    if any(unit["text"].strip() for unit in units):
        return units

    return extract_text_from_scanned_pdf(file_path)


def extract_text_from_scanned_pdf(file_path: str) -> list[dict]:
    language = os.getenv("RAG_OCR_LANGUAGE", "rus+eng")
    dpi = int(os.getenv("RAG_OCR_DPI", "200"))
    units = []

    try:
        with fitz.open(file_path) as pdf:
            for i, page in enumerate(pdf, start=1):
                text_page = page.get_textpage_ocr(
                    language=language,
                    dpi=dpi,
                    full=True,
                )
                units.append({
                    "page_start": i,
                    "page_end": i,
                    "text": page.get_text("text", textpage=text_page)
                })
    except Exception as exc:
        raise TextExtractionError(
            "Не удалось выполнить OCR для сканированного PDF. "
            "Установите Tesseract OCR и языковые пакеты rus+eng."
        ) from exc

    return units


def _iter_block_items(parent):
    if isinstance(parent, DocxDocumentType):
        parent_element = parent.element.body
    else:
        parent_element = parent._element

    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _extract_paragraph_text(paragraph):
    text = paragraph.text.strip()
    if not text:
        return ""

    style_name = paragraph.style.name.lower() if paragraph.style and paragraph.style.name else ""

    if "heading" in style_name or "заголов" in style_name:
        return f"{text}."

    return text


def _extract_table_text(table):
    rows = []

    for row in table.rows:
        cells = []
        for cell in row.cells:
            cell_text = " ".join(
                part.strip()
                for part in cell.text.splitlines()
                if part.strip()
            )
            if cell_text:
                cells.append(cell_text)

        if cells:
            rows.append(" | ".join(cells))

    if not rows:
        return ""

    return "\n".join(rows)


def extract_text_from_docx(file_path: str) -> list[dict]:
    doc = DocxDocument(file_path)
    blocks = []

    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = _extract_paragraph_text(block)
        else:
            text = _extract_table_text(block)

        if text:
            blocks.append(text)

    text = "\n\n".join(blocks)

    return [{
        "page_start": None,
        "page_end": None,
        "text": text
    }]


def extract_text_from_txt(file_path: str) -> list[dict]:
    encodings = ("utf-8-sig", "utf-8", "cp1251")

    for encoding in encodings:
        try:
            with open(file_path, encoding=encoding) as file:
                text = file.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        with open(file_path, encoding="utf-8", errors="replace") as file:
            text = file.read()

    return [{
        "page_start": None,
        "page_end": None,
        "text": text
    }]
