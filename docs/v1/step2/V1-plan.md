---
shaping: true
---

# Step 2: V1 Implementation Plan — Chunk One PDF and Save to JSON

Implements **Shape B: Block-aware accumulation with sentence fallback**.

## Files

| File | Action |
|------|--------|
| `services/chunker.py` | Rewrite |
| `scripts/chunk_pdf_inspect.py` | Unchanged |

---

## 1. Constants and `Chunk` TypedDict

```python
CHUNK_SIZE = 1024  # ~256 tokens (English ≈ 4 chars/token)

class Chunk(TypedDict):
    text: str
    page_start: int
    page_end: int
    section_path: list[str]
    section_title: str | None
    section_level: int | None
    chunk_index: int
```

---

## 2. Implement `_extract_blocks`

Returns `list[tuple[str, int]]` — `(block_text, pdf_page)` across all pages.

```python
def _extract_blocks(doc: pymupdf.Document) -> list[tuple[str, int]]:
```

- Loop `pdf_page` from 1 to `doc.page_count`
- Call `doc[pdf_page - 1].get_text("blocks")` → list of `(x0, y0, x1, y1, text, block_no, block_type)`
- Filter to text blocks only (`block_type == 0`)
- Strip whitespace from `text`; skip empty
- Append `(text, pdf_page)`

---

## 3. Implement `_split_oversized`

Splits any block that exceeds `CHUNK_SIZE` at sentence boundaries; falls back to hard slice if still oversized.

```python
import re
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

def _split_oversized(blocks: list[tuple[str, int]]) -> list[tuple[str, int]]:
```

For each `(text, page)`:
- If `len(text) <= CHUNK_SIZE`: pass through
- Else: split with `_SENTENCE_SPLIT`; if any sentence still `> CHUNK_SIZE`, hard-slice it into `CHUNK_SIZE`-sized pieces
- Each output fragment inherits the page

---

## 4. Implement `_pack_chunks`

Greedy packer; no overlap (blocks already provide natural segmentation).

```python
def _pack_chunks(fragments: list[tuple[str, int]], lookup_section) -> list[Chunk]:
```

State:
- `buffer: list[tuple[str, int]]` — current chunk's fragments
- `buffer_len: int` — total char length (sum of fragments + space joiners)
- `chunk_index: int = 0`

For each `(frag_text, page)`:
- Compute `addition = len(frag_text) + (1 if buffer else 0)` (joiner space)
- If `buffer` is non-empty AND `buffer_len + addition > CHUNK_SIZE`:
  - Emit chunk from `buffer` (see below)
  - Reset `buffer = []`, `buffer_len = 0`
- Append `(frag_text, page)` to `buffer`; update `buffer_len`

After loop: if `buffer` non-empty, emit final chunk.

**Emit chunk** helper:
- `text = " ".join(f for f, _ in buffer)`
- `page_start = buffer[0][1]`, `page_end = buffer[-1][1]`
- `section_path, section_title, section_level = lookup_section(page_start)`
- Append `Chunk(...)`, increment `chunk_index`

---

## 5. Reuse `_build_toc_section_lookup` from previous impl

Unchanged — operates on `doc.get_toc()` and returns a callable.

---

## 6. `chunk_pdf` glue

```python
def chunk_pdf(doc: pymupdf.Document) -> list[Chunk]:
    blocks = _extract_blocks(doc)
    fragments = _split_oversized(blocks)
    lookup_section = _build_toc_section_lookup(doc.get_toc())
    return _pack_chunks(fragments, lookup_section)
```

---

## 7. `save_chunks` / `load_chunks` — unchanged

```python
def save_chunks(chunks: list[Chunk], path: str | Path) -> None:
    Path(path).write_text(json.dumps(chunks, ensure_ascii=False, indent=2))

def load_chunks(path: str | Path) -> list[Chunk]:
    return json.loads(Path(path).read_text())
```

---

## 8. Debug script — unchanged

`scripts/chunk_pdf_inspect.py` continues to call `chunk_pdf`, `save_chunks`, print first 5 chunks.

---

## Done When

- `services/chunker.py` exports `Chunk`, `chunk_pdf`, `save_chunks`, `load_chunks`
- Chunks no longer cut mid-word or mid-sentence (visual inspection of sample output)
- Chunk lengths cluster near `CHUNK_SIZE` (with some variance from boundary preservation; observed avg ~836 chars / ~209 tokens on sample PDF)
- Each chunk's `page_start`/`page_end` reflect the pages of its first/last fragment
- TOC section fields populated correctly (or null/empty for pre-TOC chunks)
- `temp/chunks.json` written and reloadable
