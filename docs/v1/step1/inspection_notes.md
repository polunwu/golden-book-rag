# Step 1 PDF Inspection Notes

## Sample PDF

- Path: `temp/books/AI_ENGINEERING_BUILDING.pdf`
- Library: PyMuPDF
- PDF pages: 535
- Title: `AI Engineering`
- Author: `Chip Huyen;`
- TOC items: 182

## Checked Pages

- PDF page 1: cover text can be read.
- PDF page 7: table of contents text can be read, but dotted leaders are noisy.
- PDF page 25: chapter title and body text can be read.
- PDF page 200: body text can be read; footnote/header-like text may appear in flow.

## Notes

- `pdf_page_number` means the physical PDF page, 1-based.
- Printed book page numbers are different from PDF page numbers.
- Step 1 only proves PDF open/read/print works.
- Chunk schema fields like `page_start`, `page_end`, `section_path`, and `token_count` are for later steps.
