---
shaping: true
---

# Step 1: PDF Inspection — Shaping

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | Prove one sample PDF can be opened and read page by page | Core goal |
| R1 | Preserve page numbers so later chunks can cite source pages | Must-have |
| R2 | Inspect whether extracted text is usable for chunking | Must-have |
| R3 | Inspect layout/headings enough to know what Step 2 can rely on | Must-have |
| R4 | Keep Step 1 independent from DB, FastAPI, embeddings, and frontend | Must-have |
| R5 | Produce human-readable debug output for representative pages | Must-have |
| R6 | Document known extraction problems before moving to chunking | Must-have |

## A: Local PDF Inspection Script

| Part | Mechanism | Flag |
|------|-----------|:----:|
| A1 | Load one local PDF with PyMuPDF | |
| A2 | Iterate pages and extract text per page | |
| A3 | Print page number, text sample, and basic layout signals | |
| A4 | Manually inspect representative pages for headings, paragraphs, tables, broken text | |
| A5 | Record extraction issues in notes/output | |

## Fit Check

| Req | Requirement | Status | A |
|-----|-------------|--------|---|
| R0 | Prove one sample PDF can be opened and read page by page | Core goal | ✅ |
| R1 | Preserve page numbers so later chunks can cite source pages | Must-have | ✅ |
| R2 | Inspect whether extracted text is usable for chunking | Must-have | ✅ |
| R3 | Inspect layout/headings enough to know what Step 2 can rely on | Must-have | ✅ |
| R4 | Keep Step 1 independent from DB, FastAPI, embeddings, and frontend | Must-have | ✅ |
| R5 | Produce human-readable debug output for representative pages | Must-have | ✅ |
| R6 | Document known extraction problems before moving to chunking | Must-have | ✅ |

## Selected Shape

Use **A: Local PDF Inspection Script**.

## Slice

### Slice 1: Inspect One PDF

Input:

- One sample PDF

Output:

- Page-by-page extracted text
- Page numbers
- Representative debug printout
- Notes about heading/layout/extraction problems

Done when:

- PDF opens successfully
- Text can be extracted per page
- Page references are preserved
- Output is easy to inspect manually
- Known extraction problems are documented
- No DB/API/embedding/frontend work is introduced

## Next Step

Step 2 uses the inspection result to design chunking:

- heading detection
- section_path
- token count
- page range
