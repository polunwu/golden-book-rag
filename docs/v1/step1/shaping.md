---
shaping: true
---

# Step 1: PDF Smoke Inspection — Shaping

## Requirements (R)

| ID  | Requirement                                                                                    | Status    |
| --- | ---------------------------------------------------------------------------------------------- | --------- |
| R0  | Prove one sample PDF can be opened with PyMuPDF                                                | Core goal |
| R1  | Preserve PDF page numbers so later chunks can cite source pages                                | Must-have |
| R2  | Inspect whether extracted text from representative pages is usable for chunking                 | Must-have |
| R3  | Inspect TOC/headings/text samples enough to know what Step 2 can rely on                       | Must-have |
| R4  | Keep Step 1 independent from DB, FastAPI, embeddings, and frontend                             | Must-have |
| R5  | Produce human-readable debug output for PDF summary, TOC, and representative pages             | Must-have |
| R6  | Document known extraction problems before moving to chunking                                   | Must-have |
| R7  | Produce minimal reusable PDF functions in `services/pdf_parser.py` that Step 2 can build on    | Must-have |

## A: Local PDF Smoke Inspection Script

| Part | Mechanism                                                                                                                                 | Flag |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| A1   | Load one local PDF with PyMuPDF                                                                                                    |      |
| A2   | Extract text from selected representative PDF pages                                                                                |      |
| A3   | Print PDF summary, TOC entries, PDF page number, and text sample                                                                    |      |
| A4   | Manually inspect representative pages for headings, paragraphs, TOC noise, and broken text                                           |      |
| A5   | Record extraction issues in notes/output                                                                                           |      |
| A6   | Extract reusable functions in `services/pdf_parser.py` for opening PDFs, extracting metadata, printing doc summary, and extracting page text |      |

## Fit Check

| Req | Requirement                                                                                    | Status    | A   |
| --- | ---------------------------------------------------------------------------------------------- | --------- | --- |
| R0  | Prove one sample PDF can be opened with PyMuPDF                                                | Core goal | ✅  |
| R1  | Preserve PDF page numbers so later chunks can cite source pages                                | Must-have | ✅  |
| R2  | Inspect whether extracted text from representative pages is usable for chunking                 | Must-have | ✅  |
| R3  | Inspect TOC/headings/text samples enough to know what Step 2 can rely on                       | Must-have | ✅  |
| R4  | Keep Step 1 independent from DB, FastAPI, embeddings, and frontend                             | Must-have | ✅  |
| R5  | Produce human-readable debug output for PDF summary, TOC, and representative pages             | Must-have | ✅  |
| R6  | Document known extraction problems before moving to chunking                                   | Must-have | ✅  |
| R7  | Produce minimal reusable PDF functions in `services/pdf_parser.py` that Step 2 can build on    | Must-have | ✅  |

## Selected Shape

Use **A: Local PDF Smoke Inspection Script**.

## Slice

### Slice 1: Smoke Inspect One PDF

Input:

- One sample PDF

Output:

- PDF summary
- TOC entries
- Representative page text samples
- PDF page numbers
- Notes about heading/text/extraction problems
- Reusable functions in `services/pdf_parser.py` for PDF opening, metadata extraction, doc summary printing, and page text extraction

Done when:

- PDF opens successfully
- Text can be extracted from any requested PDF page
- PDF page references are preserved
- Output is easy to inspect manually
- Known extraction problems are documented
- Reusable PDF inspection functions exist in `services/pdf_parser.py` and can be called outside the debug script
- No DB/API/embedding/frontend work is introduced

## Next Step

Step 2 uses the inspection result to design chunking:

- heading detection
- section_path
- token count
- page range
