---
shaping: true
---

# Step 2: PDF Chunking — Shaping

## Requirements (R)

| ID  | Requirement                                                                                                                          | Status    |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| R0  | Produce text chunks targeting ~1024 chars / ~256 tokens per chunk while respecting paragraph and sentence boundaries (no mid-word/mid-sentence cuts) | Core goal |
| R1  | Each chunk has `page_start` and `page_end` (physical PDF page numbers)                                                               | Must-have |
| R2  | Each chunk has `section_path` (TEXT[]), `section_title` (TEXT), `section_level` (INT) from TOC                                       | Must-have |
| R3  | Each chunk has `chunk_index` (sequential order in book)                                                                              | Must-have |
| R4  | Chunks before first TOC entry have `section_path=[]`, `section_title=None`, `section_level=None`                                     | Must-have |
| R5  | Keep Step 2 independent from DB, embeddings, FastAPI, frontend                                                                       | Must-have |
| R6  | Output is human-readable / inspectable (print sample chunks)                                                                         | Must-have |
| R7  | Expose `chunk_pdf(doc) -> list[Chunk]` in `services/chunker.py` for Step 3                                                           | Must-have |
| R8  | Persist chunks to JSON file so Step 3 can load them before DB exists                                                                 | Must-have |

## A: Concatenate full text → fixed-size sliding window (rejected)

Fails R0 because the fixed window cuts mid-sentence and mid-word.

## B: Block-aware accumulation with sentence fallback

| Part | Mechanism                                                                                                                                                                                |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1   | For each page, call `page.get_text("blocks")` → PyMuPDF returns paragraph-like blocks with bbox + text; record `(block_text, pdf_page)` list across all pages                            |
| B2   | For any block whose text exceeds `CHUNK_SIZE`, split at sentence boundaries (regex on `(?<=[.!?])\s+`) then fallback to hard split if still too long; each fragment inherits page number |
| B3   | Greedy pack: accumulate fragments into `current_chunk` buffer until adding next fragment would exceed `CHUNK_SIZE`; emit chunk and start next with empty buffer (no overlap — blocks already provide natural segmentation) |
| B4   | Per chunk: `page_start` = page of first fragment, `page_end` = page of last fragment                                                                                                     |
| B5   | Section lookup: build TOC section map from `doc.get_toc()`; for `page_start`, return `(section_path, section_title, section_level)` or `([], None, None)` if before first TOC entry      |
| B6   | `chunk_index` = sequential 0-based int                                                                                                                                                   |
| B7   | `Chunk` TypedDict: `text, page_start, page_end, section_path, section_title, section_level, chunk_index`                                                                                 |
| B8   | `chunk_pdf(doc) -> list[Chunk]` in `services/chunker.py`                                                                                                                                 |
| B9   | `save_chunks(chunks, path)` writes JSON; `load_chunks(path) -> list[Chunk]` reads it                                                                                                     |
| B10  | Debug script: run chunker on sample PDF, save to `temp/chunks.json`, print sample                                                                                                        |

## Fit Check

| Req | Requirement                                                                       | Status    | A   | B   |
| --- | --------------------------------------------------------------------------------- | --------- | --- | --- |
| R0  | ~1024 char / ~256 token chunks respecting paragraph/sentence boundaries           | Core goal | ❌  | ✅  |
| R1  | `page_start` / `page_end`                                                         | Must-have | ✅  | ✅  |
| R2  | TOC section fields                                                                | Must-have | ✅  | ✅  |
| R3  | `chunk_index`                                                                     | Must-have | ✅  | ✅  |
| R4  | Pre-TOC chunks null/empty                                                         | Must-have | ✅  | ✅  |
| R5  | Independent from DB/embeddings/API/frontend                                       | Must-have | ✅  | ✅  |
| R6  | Inspectable output                                                                | Must-have | ✅  | ✅  |
| R7  | `chunk_pdf` exposed                                                               | Must-have | ✅  | ✅  |
| R8  | JSON persistence                                                                  | Must-have | ✅  | ✅  |

## Selected Shape

Use **B: Block-aware accumulation with sentence fallback**.

## Slice

### Slice 1: Chunk One PDF and Save to JSON

Input:

- One sample PDF (via `open_pdf` from `services/pdf_parser.py`)

Output:

- `list[Chunk]` in memory
- `temp/chunks.json` with all chunks serialized

Done when:

- Chunks respect paragraph and sentence boundaries (no mid-word/mid-sentence cuts)
- Chunk sizes target ~1024 chars / ~256 tokens (allow variance for boundary preservation)
- Each chunk has correct `page_start`/`page_end` from fragment page numbers
- Each chunk has `section_path`/`section_title`/`section_level` from TOC (or null/empty if before first TOC entry)
- Each chunk has `chunk_index`
- `temp/chunks.json` is written and can be reloaded with `load_chunks`
- Sample chunks are printed for manual inspection
- No DB/API/embedding/frontend work is introduced

## Next Step

Step 3 uses `load_chunks("temp/chunks.json")` and sends each chunk's `text` to OpenAI `text-embedding-3-small` to generate embedding vectors.
