---
shaping: true
---

# Step 2: V1 Implementation Plan — Chunk One PDF and Save to JSON

## Files

| File | Action |
|------|--------|
| `services/chunker.py` | Create |
| `scripts/chunk_pdf_inspect.py` | Create |

---

## 1. Define `Chunk` TypedDict in `services/chunker.py`

```python
from typing import TypedDict

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

## 2. Implement `_build_page_offsets`

Extracts all page texts, concatenates into one string, tracks char boundaries per page.

```python
def _build_page_offsets(doc: pymupdf.Document) -> tuple[str, list[tuple[int, int, int]]]:
    # returns (full_text, [(char_start, char_end, pdf_page), ...])
```

- Loop `pdf_page` from 1 to `doc.page_count`
- Call `extract_page_text(doc, pdf_page)` from `services/pdf_parser.py`
- Append `(len(full_text_so_far), len(full_text_so_far) + len(page_text), pdf_page)`
- Concatenate page text into `full_text`

---

## 3. Implement `_char_to_page`

Binary-searches `page_offsets` to find which PDF page a char position belongs to.

```python
import bisect

def _char_to_page(page_offsets: list[tuple[int, int, int]], pos: int) -> int:
    starts = [s for s, _, _ in page_offsets]
    idx = max(0, bisect.bisect_right(starts, pos) - 1)
    return page_offsets[idx][2]
```

---

## 4. Implement `_build_toc_section_lookup`

Returns a callable that, given a PDF page number, returns `(section_path, section_title, section_level)`.

```python
def _build_toc_section_lookup(toc: list[tuple[int, str, int]]):
    # toc entries: (level, title, pdf_page), sorted by pdf_page
```

Logic:
- Iterate TOC entries in order (they are page-ordered)
- Maintain `active: dict[int, str]` — level → title of most recent heading at that level
- When a level-N entry is encountered: delete all keys `>= N` from `active`, then set `active[N] = title`
- Store `(pdf_page, snapshot of active)` for each entry

Lookup for page P:
- Find the last entry with `pdf_page <= P`
- If none: return `([], None, None)`
- From `active` snapshot: `section_path = [active[l] for l in sorted(active)]`, `section_title = active[max(active)]`, `section_level = max(active)`

---

## 5. Implement `chunk_pdf`

```python
CHUNK_SIZE = 500
OVERLAP = 50
STEP = CHUNK_SIZE - OVERLAP  # 450

def chunk_pdf(doc: pymupdf.Document) -> list[Chunk]:
```

Steps:
1. Call `_build_page_offsets(doc)` → `full_text`, `page_offsets`
2. Call `_build_toc_section_lookup(doc.get_toc())` → `lookup_section`
3. Slide window: `i = 0`, `chunk_index = 0`; while `i < len(full_text)`:
   - `text = full_text[i : i + CHUNK_SIZE]`
   - `page_start = _char_to_page(page_offsets, i)`
   - `page_end = _char_to_page(page_offsets, min(i + CHUNK_SIZE - 1, len(full_text) - 1))`
   - `section_path, section_title, section_level = lookup_section(page_start)`
   - Append `Chunk(text=text, page_start=page_start, page_end=page_end, section_path=section_path, section_title=section_title, section_level=section_level, chunk_index=chunk_index)`
   - `chunk_index += 1`, `i += STEP`
4. Return chunks

---

## 6. Implement `save_chunks` and `load_chunks`

```python
import json
from pathlib import Path

def save_chunks(chunks: list[Chunk], path: str | Path) -> None:
    Path(path).write_text(json.dumps(chunks, ensure_ascii=False, indent=2))

def load_chunks(path: str | Path) -> list[Chunk]:
    return json.loads(Path(path).read_text())
```

---

## 7. Create `scripts/chunk_pdf_inspect.py`

```python
from services.pdf_parser import open_pdf
from services.chunker import chunk_pdf, save_chunks

OUTPUT = "temp/chunks.json"
PDF = "temp/books/AI_ENGINEERING_BUILDING.pdf"

doc = open_pdf(PDF)
chunks = chunk_pdf(doc)
save_chunks(chunks, OUTPUT)

print(f"Total chunks: {len(chunks)}")
print()
for chunk in chunks[:5]:
    print(
        f"[{chunk['chunk_index']}]"
        f" pages {chunk['page_start']}-{chunk['page_end']}"
        f" | level={chunk['section_level']}"
        f" | path={chunk['section_path']}"
    )
    print(f"  {chunk['text'][:120]!r}")
    print()
```

---

## Done When

- `services/chunker.py` exports `Chunk`, `chunk_pdf`, `save_chunks`, `load_chunks`
- Running `scripts/chunk_pdf_inspect.py` prints chunks with correct page ranges and section fields
- `temp/chunks.json` is written and can be reloaded with `load_chunks`
- Chunks before the first TOC entry show `section_path=[]`, `section_title=None`, `section_level=None`
- No DB / embedding / FastAPI code introduced
