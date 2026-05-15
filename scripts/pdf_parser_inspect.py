from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

import pymupdf

from services.pdf_parser import extract_page_text, extract_pdf_metadata, open_pdf


PDF_PATH = ROOT_DIR / "temp/books/AI_ENGINEERING_BUILDING.pdf"
PDF_PAGE_NUMBERS = [1, 7, 25, 200]
SAMPLE_CHARS = 500


def print_pdf_summary(doc: pymupdf.Document) -> None:
    metadata = extract_pdf_metadata(doc)
    toc = metadata["toc"]
    print(f"PDF: {metadata['path']}")
    print(f"Title: {metadata['title']}")
    print(f"Author: {metadata['author']}")
    print(f"PDF pages: {metadata['pdf_pages']}")
    print(f"TOC items length: {len(toc)}")
    print("TOC items:")
    for level, title, page in toc:
        print(f"level={level} page={page} title={title}")


def main() -> None:
    with open_pdf(PDF_PATH) as doc:
        print_pdf_summary(doc)
        for pdf_page_number in PDF_PAGE_NUMBERS:
            text = extract_page_text(doc, pdf_page_number)
            print()
            print(f"--- PDF page {pdf_page_number} ---")
            print(text[:SAMPLE_CHARS].rstrip())


if __name__ == "__main__":
    main()
