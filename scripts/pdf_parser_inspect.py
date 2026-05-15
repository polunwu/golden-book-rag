import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.pdf_parser import extract_page_text, open_pdf, print_pdf_summary


PDF_PATH = ROOT_DIR / "temp/books/AI_ENGINEERING_BUILDING.pdf"
PDF_PAGE_NUMBERS = [1, 7, 25, 200]
SAMPLE_CHARS = 500


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
