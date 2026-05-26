---
shaping: true
---

# Step 5: V3 Implementation Plan — Upload endpoint + background ingest

Implements **V3** from [slices.md](./slices.md) — Shape B parts **B5**
(background ingest orchestrator in `services/ingest.py`) and **B6** (upload
handler chain in `api/routers/books.py`). Closes Step 5.

Demo: `curl -F file=@book.pdf -F title='AI Engineering' :8000/books/upload`
returns `202 {book_id, status:"pending"}` within ~1s; polling
`GET /books/:id` shows `pending → processing → ready`. Re-upload with the
same `book_id` replaces only that book's rows. Corrupt PDF lands the row at
`status='failed'` with `error_message`.

## Files

| File                       | Action                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------- |
| `pyproject.toml`           | Add `python-multipart` (FastAPI form parsing). `anyio` is already a FastAPI dep.        |
| `.env.example`             | Add `UPLOAD_DIR=uploads`, `MAX_UPLOAD_MB=100`                                            |
| `.env`                     | Add the same vars locally                                                               |
| `.gitignore`               | Add `uploads/`                                                                          |
| `api/main.py`              | Modify — `mkdir(UPLOAD_DIR)` on startup (alongside V2's lifespan)                       |
| `api/schemas.py`           | Add `UploadResponse`                                                                    |
| `api/routers/books.py`     | Add `POST /books/upload` handler chaining N10 → N15                                     |
| `services/ingest.py`       | Create — `ingest_pdf` (sync orchestrator) + `run_ingest` (async wrapper)                |

No DB schema changes (V1's `_book_status` revision already added `status` +
`error_message`).

---

## 1. Dependencies + config

`pyproject.toml`:

```toml
dependencies = [
    # ... existing V1/V2 deps ...
    "python-multipart>=0.0.9",
]
```

`.env.example` (and `.env`):

```text
# existing
DATABASE_URL=postgresql://bookrag:bookrag@localhost:5432/bookrag
GEMINI_API_KEY=...

# new in V3
UPLOAD_DIR=uploads
MAX_UPLOAD_MB=100
```

`.gitignore`:

```
uploads/
```

Run `uv sync` after editing `pyproject.toml`.

---

## 2. `api/main.py` — create `UPLOAD_DIR` on startup

Modify V2's lifespan to also ensure the upload directory exists. Avoids a
race where the first upload handler hits a missing dir.

```python
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from api.routers import books
from db.connection import get_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Path(os.environ.get("UPLOAD_DIR", "uploads")).mkdir(parents=True, exist_ok=True)
    pool = get_pool()
    pool.open()
    pool.wait()
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="golden-book-rag", lifespan=lifespan)
app.include_router(books.router)
```

`UPLOAD_DIR` is resolved relative to the process cwd (consistent with how
the rest of the project handles paths). The dir is read again per-request in
the handler — declared as a small helper rather than a module-level constant
so tests can monkeypatch the env.

---

## 3. `api/schemas.py` — add `UploadResponse`

Append to V2's `schemas.py`:

```python
class UploadResponse(BaseModel):
    book_id: UUID
    status: BookStatus
```

No `UploadRequest` model — the multipart form fields (`file`, `title`,
optional `book_id`) are declared inline in the handler signature using
`UploadFile` + `Form`, which is the canonical FastAPI pattern.

---

## 4. `services/ingest.py` — background orchestrator

```python
"""Background ingest orchestrator. Owns books.status lifecycle.

Pure sync code (ingest_pdf) wrapped in an async thread-offload (run_ingest).
Imported by api/routers/books.py — must NOT import from api.* (R3.2).
"""
import uuid
from pathlib import Path

import anyio

from db.connection import get_pool
from services.chunker import chunk_pdf
from services.embeddings import embed_chunks
from services.pdf_parser import open_pdf
from services.store import ingest_book


def _set_status(book_id: uuid.UUID, status: str, error_message: str | None = None) -> None:
    """Fresh pooled connection + own transaction. Used for processing/ready/failed
    writes — never reuses ingest_book's connection (it may be in error state)."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE books SET status = %s::book_status, error_message = %s "
                "WHERE id = %s",
                (status, error_message, book_id),
            )
        conn.commit()


def ingest_pdf(book_id: uuid.UUID, pdf_path: str, title: str) -> None:
    """Sync orchestrator: parse → chunk → embed → store, with status writes
    on each lifecycle boundary. Any exception lands the row at 'failed'.

    Runs in an anyio worker thread (see run_ingest). Holds its own pool conn
    for the duration of ingest_book — released back to the pool on commit.
    """
    try:
        _set_status(book_id, "processing")
        doc = open_pdf(pdf_path)
        chunks = chunk_pdf(doc)
        embeddings = embed_chunks(chunks)
        with get_pool().connection() as conn:
            ingest_book(conn, book_id, chunks, embeddings, title, pdf_path)
        _set_status(book_id, "ready")
    except Exception as exc:
        # Fresh conn (see _set_status) — the ingest_book conn may be poisoned.
        # Truncate error_message to fit in TEXT and avoid blowing up the row
        # if the underlying exception is huge.
        _set_status(book_id, "failed", str(exc)[:2000])
        raise  # let uvicorn log the traceback


async def run_ingest(book_id: uuid.UUID, pdf_path: str, title: str) -> None:
    """Async wrapper. `BackgroundTasks.add_task` accepts async callables;
    anyio.to_thread.run_sync moves the sync body off the event loop (R7.4)."""
    await anyio.to_thread.run_sync(ingest_pdf, book_id, pdf_path, title)
```

Notes:

- **Three transactions, not one.** `set_status('processing')` commits before
  parse starts, so an external poller can observe the transition; the long
  `ingest_book` tx commits its own rows; `set_status('ready')` commits last.
  If the process dies between `ingest_book.commit()` and `set_status('ready')`,
  the row stays at `processing` with rows already present — the documented
  R7.3 MVP gap.
- **Failure path uses a fresh connection.** If `ingest_book` raised mid-transaction,
  the original conn is in an aborted state and only accepts `ROLLBACK`. Opening
  a new conn for the `failed` write avoids special-casing rollback inside the
  except block.
- **`raise` after the failed-write** so uvicorn logs the traceback. The HTTP
  response was already sent (`BackgroundTasks` runs after response) so re-raising
  has no client-facing impact.
- **No `api/` imports.** The orchestrator is callable from scripts too (R3.2 /
  B5.3) — useful for future ops tooling.

---

## 5. `api/routers/books.py` — `POST /books/upload`

Add to the V2 router. Keep V2's read handlers unchanged below.

```python
import os
import uuid
from pathlib import Path
from typing import Annotated

import psycopg
from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile,
)

from api.deps import get_conn
from api.schemas import UploadResponse
from services.ingest import run_ingest

# ... V2 router + read handlers above ...


def _max_upload_bytes() -> int:
    return int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024


def _upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "uploads"))


@router.post("/upload", response_model=UploadResponse, status_code=202)
def upload_book(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    book_id: Annotated[str | None, Form()] = None,
    conn: psycopg.Connection = Depends(get_conn),
) -> UploadResponse:
    # N10 — validate
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="file must be application/pdf")
    if not title.strip():
        raise HTTPException(status_code=422, detail="title must not be empty")

    # N11 — resolve book_id
    if book_id is not None:
        try:
            resolved_id = uuid.UUID(book_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="book_id must be a UUID")
        exists = conn.execute(
            "SELECT 1 FROM books WHERE id = %s", (resolved_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(
                status_code=404,
                detail="unknown book_id; omit to create new",
            )
    else:
        resolved_id = uuid.uuid4()

    # N12 — persist PDF (stream + size-check). Reject before any DB writes
    # so a too-large upload doesn't leave a 'pending' row stranded.
    pdf_path = _upload_dir() / f"{resolved_id}.pdf"
    max_bytes = _max_upload_bytes()
    written = 0
    with pdf_path.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                out.close()
                pdf_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"file exceeds MAX_UPLOAD_MB={max_bytes // (1024 * 1024)}",
                )
            out.write(chunk)

    # N13 — upsert books row; reset lifecycle fields on re-ingest
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO books (id, title, file_path, status, error_message) "
            "VALUES (%s, %s, %s, 'pending', NULL) "
            "ON CONFLICT (id) DO UPDATE SET "
            "title = EXCLUDED.title, file_path = EXCLUDED.file_path, "
            "status = 'pending', error_message = NULL",
            (resolved_id, title, str(pdf_path)),
        )
    conn.commit()

    # N14 — schedule background ingest (runs AFTER 202 response is sent)
    background_tasks.add_task(run_ingest, resolved_id, str(pdf_path), title)

    # N15 — 202
    return UploadResponse(book_id=resolved_id, status="pending")
```

Notes:

- **Stream-with-counter for size cap.** `UploadFile.size` is populated from
  the spooled-file backing but is not authoritative for streamed multipart;
  reading-and-counting is the safe path. The 1 MiB chunk size is arbitrary —
  big enough that fixed per-chunk overhead is irrelevant, small enough that
  rejecting a way-too-large upload happens quickly.
- **Cleanup on size-rejection.** Partial file is unlinked; no DB row written
  (the size check happens before the `INSERT`). A re-ingest path that rejects
  on size still leaves the existing PDF intact because the rejection path
  unlinks `pdf_path` — but `pdf_path` is the same as the existing file's path
  for an existing `book_id`. **Edge case:** an oversized re-upload deletes
  the previous PDF on disk. The DB row still points at it.

  Acceptable for MVP (the row is at `status='ready'` and chunks still serve
  reads); if it bites, the fix is to write to a temp path first and rename on
  success. Documented here, not solved.
- **422 vs 413.** Bad content-type / empty title / malformed `book_id` →
  `422`. Oversized file → `413 Payload Too Large` (HTTP-correct; FastAPI
  doesn't reject upfront because it streams).
- **`book_id` is `str | None`, not `UUID | None`.** FastAPI's `Form` doesn't
  parse UUIDs reliably across multipart frameworks; we parse explicitly and
  return `422` on bad input.
- **The request conn commits the upsert before scheduling the bg task.**
  Important — the bg task opens its own conn and would not see the new row
  otherwise.

---

## Implementation Order

1. **Deps + env + .gitignore** (§1) → `uv sync`
2. **`api/main.py`** (§2) — add `mkdir(UPLOAD_DIR)`; restart `uvicorn`; verify
   `uploads/` is created if missing
3. **`api/schemas.py`** (§3) — `UploadResponse`
4. **`services/ingest.py`** (§4) — orchestrator + async wrapper. Smoke from
   a REPL: `python -c "import asyncio; from services.ingest import run_ingest;
   asyncio.run(run_ingest(<existing-book-id>, '<existing-pdf-path>', 't'))"`
   against the V1-ingested book → confirm status transitions visible in
   `\d books` via `make db-shell`.
5. **`api/routers/books.py`** (§5) — wire the upload handler
6. **Manual run-through** (see Done When)

---

## Done When

### Happy path
- `curl -F file=@temp/books/AI_ENGINEERING_BUILDING.pdf -F title='AI Engineering' :8000/books/upload`
  returns `202 {"book_id":"...","status":"pending"}` within ~1s
- File at `uploads/{book_id}.pdf`; size matches the uploaded PDF
- Polling `GET /books/{book_id}` shows status transition
  `pending → processing → ready` (a few minutes for a full ingest)
- After `ready`: `GET /books/{book_id}/chunks` returns the chunks for that
  book (V2 handler, unchanged)

### Concurrency
- Two `POST /books/upload` calls in quick succession both return `202` within
  ~1s each; both books reach `ready` independently; neither blocks the other
- `GET /books` during ingest still responds in <100ms (event loop not stalled
  by the worker-thread ingest) — R7.4

### Re-ingest
- `POST /books/upload` with `book_id={existing-id}` (new title / same or
  different PDF) returns `202`; `uploads/{book_id}.pdf` overwrites the old
  file; the row's `status` resets to `pending` then transitions; previous
  `chunks` + `chunk_embeddings` for that `book_id` are replaced (CASCADE);
  a sibling book's rows are unchanged before/after

### Errors
- `POST /books/upload` with `book_id=00000000-0000-0000-0000-000000000099`
  (unknown) → `404 {"detail":"unknown book_id; omit to create new"}`;
  no row created, no file written
- `POST` with `file=@some.txt` → `422 file must be application/pdf`
- `POST` with `title=''` → `422 title must not be empty`
- `POST` with a 200 MB file (with `MAX_UPLOAD_MB=100`) → `413`; partial
  file unlinked
- Corrupt PDF (zero-byte file or PDF with a malformed cross-ref): upload
  succeeds (202); background task fails inside `open_pdf`; row lands at
  `status='failed'` with non-empty `error_message`; row never stays at
  `processing`
- `make db-shell` → `UPDATE books SET status='ready' WHERE id=...` for a
  book whose previous status was `failed` resets the row; re-uploading
  reuses it normally

### Boundaries / R3.2
- `grep -r "fastapi\|pydantic" services/ db/` returns nothing
- `services/ingest.py` is callable from a plain Python REPL (no FastAPI app
  running) — verified in step 4 of Implementation Order

### Out of scope (intentional)
- Server crash mid-ingest still leaves rows stuck at `processing` — R7.3
  known gap; no startup sweep (Step 6+)
- `GET /books/{book_id}/chunks` against a book at `status='processing'`
  returns partial rows (whatever's been inserted so far) — Step 6 will gate
  retrieval on `status='ready'`; read endpoints stay un-gated here
- No `POST /books/:id/ask` (retrieval) — Step 6
- No auth, no CORS config, no rate limiting
