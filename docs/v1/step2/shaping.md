---
shaping: true
---

# Step 2: PDF Chunking — Shaping

## Requirements (R)

| ID  | Requirement                                                                                           | Status    |
| --- | ----------------------------------------------------------------------------------------------------- | --------- |
| R0  | Produce text chunks using fixed-size sliding window (500 chars, 50 chars overlap)                     | Core goal |
| R1  | Each chunk has `page_start` and `page_end` (physical PDF page numbers)                                | Must-have |
| R2  | Each chunk has `section_path` (TEXT[]), `section_title` (TEXT), `section_level` (INT) from TOC       | Must-have |
| R3  | Each chunk has `chunk_index` (sequential order in book)                                               | Must-have |
| R4  | Chunks before first TOC entry have `section_path=[]`, `section_title=None`, `section_level=None`      | Must-have |
| R5  | Keep Step 2 independent from DB, embeddings, FastAPI, frontend                                        | Must-have |
| R6  | Output is human-readable / inspectable (print sample chunks)                                          | Must-have |
| R7  | Expose `chunk_pdf(doc) -> list[Chunk]` in `services/chunker.py` for Step 3                            | Must-have |
| R8  | Persist chunks to JSON file so Step 3 can load them before DB exists                                  | Must-have |

## A: Concatenate full text → sliding window → annotate with TOC → save JSON

| Part | Mechanism                                                                                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1   | Extract all pages with `extract_page_text`; concatenate into one string; build `page_offsets: list[(char_start, char_end, pdf_page)]`                               |
| A2   | Build TOC section map from `doc.get_toc()`; for page P, binary-search to find active entry per level; compose `section_path`, `section_title`, `section_level`; return `[]`/`None`/`None` if before first TOC entry |
| A3   | Slide window over full text: window=500, step=450                                                                                                                   |
| A4   | Per chunk: resolve `page_start`/`page_end` from `page_offsets`; resolve section fields from TOC map at `page_start`                                                 |
| A5   | `chunk_index` = sequential 0-based int                                                                                                                              |
| A6   | `Chunk` TypedDict: `text, page_start, page_end, section_path, section_title, section_level, chunk_index`                                                            |
| A7   | `chunk_pdf(doc) -> list[Chunk]` in `services/chunker.py`                                                                                                            |
| A8   | `save_chunks(chunks, path)` writes JSON; `load_chunks(path) -> list[Chunk]` reads it — both in `services/chunker.py`                                                |
| A9   | Debug script: run chunker on sample PDF, save to `temp/chunks.json`, print sample                                                                                   |

## Fit Check

| Req | Requirement                                                                                     | Status    | A   |
| --- | ----------------------------------------------------------------------------------------------- | --------- | --- |
| R0  | Produce text chunks using fixed-size sliding window (500 chars, 50 chars overlap)               | Core goal | ✅  |
| R1  | Each chunk has `page_start` and `page_end`                                                      | Must-have | ✅  |
| R2  | Each chunk has `section_path`, `section_title`, `section_level` from TOC                        | Must-have | ✅  |
| R3  | Each chunk has `chunk_index`                                                                    | Must-have | ✅  |
| R4  | Pre-TOC chunks return null/empty section fields                                                 | Must-have | ✅  |
| R5  | Independent from DB, embeddings, FastAPI, frontend                                              | Must-have | ✅  |
| R6  | Human-readable / inspectable output                                                             | Must-have | ✅  |
| R7  | `chunk_pdf(doc) -> list[Chunk]` in `services/chunker.py`                                        | Must-have | ✅  |
| R8  | Persist chunks to JSON for Step 3                                                               | Must-have | ✅  |

## Selected Shape

Use **A: Concatenate full text → sliding window → annotate with TOC → save JSON**.

## Slice

### Slice 1: Chunk One PDF and Save to JSON

Input:

- One sample PDF (via `open_pdf` from `services/pdf_parser.py`)

Output:

- `list[Chunk]` in memory
- `temp/chunks.json` with all chunks serialized

Done when:

- Full PDF text is extracted and concatenated
- Sliding window produces chunks at correct positions (window=500, step=450)
- Each chunk has correct `page_start`/`page_end` resolved from page offsets
- Each chunk has `section_path`/`section_title`/`section_level` from TOC (or null/empty if before first TOC entry)
- Each chunk has `chunk_index`
- `temp/chunks.json` is written and can be reloaded with `load_chunks`
- Sample chunks are printed for manual inspection
- No DB/API/embedding/frontend work is introduced

## Next Step

Step 3 uses `load_chunks("temp/chunks.json")` and sends each chunk's `text` to OpenAI `text-embedding-3-small` to generate embedding vectors.
