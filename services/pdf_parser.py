from pathlib import Path
from typing import TypeAlias, TypedDict, cast

import pymupdf


TocEntry: TypeAlias = tuple[int, str, int]
Toc: TypeAlias = list[TocEntry]


class PdfMetadata(TypedDict):
    path: str
    title: str | None
    author: str | None
    pdf_pages: int
    toc: Toc


def open_pdf(path: str | Path) -> pymupdf.Document:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    return pymupdf.open(pdf_path)


def extract_pdf_metadata(doc: pymupdf.Document) -> PdfMetadata:
    metadata = doc.metadata or {}
    return {
        "path": cast(str, doc.name),
        "title": cast(str | None, metadata.get("title")),
        "author": cast(str | None, metadata.get("author")),
        "pdf_pages": doc.page_count,
        "toc": cast(Toc, doc.get_toc()),
    }


def extract_page_text(doc: pymupdf.Document, pdf_page_number: int) -> str:
    if pdf_page_number < 1:
        raise ValueError("pdf_page_number must be >= 1")

    if pdf_page_number > doc.page_count:
        raise ValueError(
            f"pdf_page_number {pdf_page_number} exceeds PDF pages {doc.page_count}"
        )
    return cast(str, doc[pdf_page_number - 1].get_text("text"))
