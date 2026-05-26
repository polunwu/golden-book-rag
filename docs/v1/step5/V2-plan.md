---
shaping: true
---

# Step 5: V2 Implementation Plan — FastAPI shell + read endpoints

Implements **V2** from [slices.md](./slices.md) — Shape B parts **B1**
(FastAPI app package), **B2** (`psycopg_pool` in `db/connection.py`), **B7**
(read handlers), and **B8** (config / boundaries). No upload, no background
ingest (V3).

Demo: `uvicorn api.main:app` boots without applying migrations (R4.2);
`GET /books` returns the V1-ingested book; `GET /books/:id/chunks?limit=3&offset=0`
paginates with `total=1286`; `limit=300` is rejected with `422`.

## Files

| File                       | Action                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------- |
| `pyproject.toml`           | Add `fastapi`, `uvicorn[standard]`, `psycopg_pool`; add `api` to wheel packages         |
| `db/connection.py`         | Add `get_pool()` (lazy module-level `ConnectionPool`); keep `get_connection()`          |
| `api/__init__.py`          | Create (empty)                                                                          |
| `api/main.py`              | Create — `FastAPI()`, `lifespan` opens/closes pool, mount books router                  |
| `api/deps.py`              | Create — `get_conn` dependency yielding a pooled connection                             |
| `api/schemas.py`           | Create — `BookOut`, `BookList`, `ChunkOut`, `ChunkPage`, `ErrorOut`                     |
| `api/routers/__init__.py`  | Create (empty)                                                                          |
| `api/routers/books.py`     | Create — `list_books`, `get_book`, `get_chunks` handlers (no upload yet)                |

No env changes (still `DATABASE_URL` + `GEMINI_API_KEY` from Step 4 / Step 3).

---

## 1. Dependencies + packaging

`pyproject.toml`:

```toml
dependencies = [
    "pymupdf>=1.27.2.3",
    "google-genai>=1.0",
    "tenacity>=9.0",
    "python-dotenv>=1.0",
    "numpy>=2.0",
    "psycopg[binary]>=3.2",
    "psycopg_pool>=3.2",
    "pgvector>=0.3",
    "alembic>=1.13",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]
```

```toml
[tool.hatch.build.targets.wheel]
packages = ["services", "db", "api"]
```

Adding `api` keeps `from api.deps import get_conn` importable across the
project; `uvicorn` is the dev server (`uv run uvicorn api.main:app --reload`).
Run `uv sync` after editing.

---

## 2. `db/connection.py` — add `get_pool()` alongside `get_connection()`

```python
import os
from typing import Optional

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

load_dotenv()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing — set in .env or environment")
    return url


_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    """Lazy module-level pool. Every checked-out connection has the pgvector
    adapter registered via `configure=register_vector` (B2.1).

    Lifecycle: `api/main.py`'s lifespan calls `.open()` on startup and `.close()`
    on shutdown. Scripts MUST NOT call get_pool() — they use get_connection().
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_database_url(),
            min_size=1,
            max_size=10,
            configure=register_vector,
            open=False,  # explicit open in lifespan; avoids work at import time
        )
    return _pool


def get_connection() -> psycopg.Connection:
    """Single-connection accessor for scripts. Unchanged from Step 4 / V1."""
    conn = psycopg.connect(_database_url())
    register_vector(conn)
    return conn
```

`configure=register_vector` runs once per connection when the pool checks one
out — guarantees every handler sees registered `vector` types (eliminates
"forgot to register" bugs that would surface as opaque encoding errors at
`<=>` query time). `open=False` defers socket work until lifespan runs, so
imports stay side-effect-free (matters for tests).

`get_connection()` is preserved verbatim — V1 scripts (`store_pdf_inspect.py`,
`probe_pgvector.py`, `embed_pdf_inspect.py`) keep working untouched (B2.2).

---

## 3. `api/__init__.py`, `api/routers/__init__.py`

Empty files — make `api` and `api.routers` importable packages.

---

## 4. `api/schemas.py` — Pydantic request/response models

```python
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

BookStatus = Literal["pending", "processing", "ready", "failed"]


class BookOut(BaseModel):
    id: UUID
    title: str | None
    file_path: str | None
    created_at: datetime
    status: BookStatus
    error_message: str | None = None


class BookList(BaseModel):
    items: list[BookOut]


class ChunkOut(BaseModel):
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: list[str] | None
    section_title: str | None
    section_level: int | None


class ChunkPage(BaseModel):
    items: list[ChunkOut]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    detail: str
```

`BookStatus` mirrors the `book_status` enum from V1's `_book_status` revision.
`ErrorOut` is the shape FastAPI uses for `HTTPException` responses by default;
declared here so the OpenAPI schema is explicit (no behaviour change).
V3 adds `UploadResponse` to this file.

---

## 5. `api/deps.py` — `get_conn` dependency

```python
from typing import Iterator

import psycopg

from db.connection import get_pool


def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection for the duration of one request.

    The `with` block returns the connection to the pool on exit (and rolls back
    on exception). Handlers depend on this — never call get_pool() directly
    from a handler (defeats request-scoped lifecycle).
    """
    with get_pool().connection() as conn:
        yield conn
```

Sync generator → FastAPI runs the dep + handler in a worker thread (default
for sync deps), so psycopg's blocking I/O does not stall the event loop.
A handler that does pure async work could swap to a pool-backed async conn
later, but V2 stays sync end-to-end.

---

## 6. `api/main.py` — app + lifespan

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from api.routers import books
from db.connection import get_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = get_pool()
    pool.open()
    pool.wait()           # block until min_size conns are healthy
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="golden-book-rag", lifespan=lifespan)
app.include_router(books.router)
```

`lifespan` does **not** call `alembic upgrade head` — explicit-setup via
`make db-migrate` (R4.2, R5 hand-off). `pool.wait()` makes startup fail fast
if `DATABASE_URL` is wrong, instead of silently deferring the error to the
first request.

---

## 7. `api/routers/books.py` — read handlers

```python
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_conn
from api.schemas import BookList, BookOut, ChunkOut, ChunkPage

router = APIRouter(prefix="/books", tags=["books"])

_BOOK_COLS = "id, title, file_path, created_at, status, error_message"
_CHUNK_COLS = (
    "chunk_index, text, page_start, page_end, "
    "section_path, section_title, section_level"
)


def _row_to_book(row: tuple) -> BookOut:
    return BookOut(
        id=row[0], title=row[1], file_path=row[2], created_at=row[3],
        status=row[4], error_message=row[5],
    )


def _row_to_chunk(row: tuple) -> ChunkOut:
    return ChunkOut(
        chunk_index=row[0], text=row[1], page_start=row[2], page_end=row[3],
        section_path=row[4], section_title=row[5], section_level=row[6],
    )


@router.get("", response_model=BookList)
def list_books(conn: psycopg.Connection = Depends(get_conn)) -> BookList:
    rows = conn.execute(
        f"SELECT {_BOOK_COLS} FROM books ORDER BY created_at DESC"
    ).fetchall()
    return BookList(items=[_row_to_book(r) for r in rows])


@router.get("/{book_id}", response_model=BookOut)
def get_book(
    book_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> BookOut:
    row = conn.execute(
        f"SELECT {_BOOK_COLS} FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")
    return _row_to_book(row)


@router.get("/{book_id}/chunks", response_model=ChunkPage)
def get_chunks(
    book_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_conn),
) -> ChunkPage:
    exists = conn.execute(
        "SELECT 1 FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="book not found")

    total_row = conn.execute(
        "SELECT count(*) FROM chunks WHERE book_id = %s", (book_id,)
    ).fetchone()
    assert total_row is not None
    total = total_row[0]

    rows = conn.execute(
        f"SELECT {_CHUNK_COLS} FROM chunks WHERE book_id = %s "
        f"ORDER BY chunk_index LIMIT %s OFFSET %s",
        (book_id, limit, offset),
    ).fetchall()
    return ChunkPage(
        items=[_row_to_chunk(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )
```

Notes:
- `UUID` path param → FastAPI auto-validates; malformed id → `422` before
  the handler runs.
- `Query(ge=…, le=…)` → `422` for `limit=0` / `limit=300` / `offset<0` (R2.3).
- `_BOOK_COLS` / `_CHUNK_COLS` are private constants in this module → not
  dynamic SQL from user input, so `psycopg.sql.SQL` / `Identifier` is not
  needed here (vs `scripts/probe_pgvector.py` which interpolates `EMBEDDING_DIM`).
- Existence check on `book_id` for `get_chunks` is a separate `SELECT 1` —
  one extra round-trip per request, but distinguishes "unknown book" (404)
  from "known book, empty page" (200 with empty items). Acceptable for read
  traffic at MVP scale.

V3 will add `POST /books/upload` to this same module (B6).

---

## Implementation Order

1. **Deps** (§1) → `uv sync` (pulls `fastapi`, `uvicorn`, `psycopg_pool`)
2. **`db/connection.py`** (§2) — add `get_pool()`; verify Step 4 / V1 scripts
   still run (`uv run python scripts/probe_pgvector.py`,
   `uv run python scripts/store_pdf_inspect.py`)
3. **`api/` skeleton** (§§3–6): empty `__init__.py`s, then `schemas.py`,
   `deps.py`, `main.py` with one trivial handler temporarily (`@app.get("/health")`)
   to verify boot
4. **Boot smoke** — `uv run uvicorn api.main:app --reload`; logs show
   `Application startup complete`; pool messages visible; no DDL ran
5. **`api/routers/books.py`** (§7) — wire the three handlers; remove the
   `/health` placeholder
6. **Curl checks** (see Done When)

---

## Done When

- `uv sync` installs `fastapi`, `uvicorn[standard]`, `psycopg_pool`
- `uv run uvicorn api.main:app` boots; logs show pool open + "Application
  startup complete"; **no Alembic / DDL output** (R4.2 — verified by running
  `uv run alembic stamp base` first, booting, and confirming `\d books` is
  unchanged)
- `Ctrl-C` shuts down cleanly; pool close visible in logs
- `curl :8000/books` returns `{"items":[{...}]}` with the V1-ingested book
  (status appears as `"pending"` since V1 doesn't write status)
- `curl :8000/books/<v1-book-id>` returns the same `BookOut`; unknown UUID
  returns `404 {"detail":"book not found"}`; malformed UUID returns `422`
- `curl ':8000/books/<id>/chunks?limit=3&offset=0'` returns
  `{"items":[...3...], "total":1286, "limit":3, "offset":0}`
- `?limit=300` → `422`; `?limit=0` → `422`; `?offset=-1` → `422`
- `curl ':8000/books/<id>/chunks?limit=50&offset=1280'` returns 6 items
  (1286 total → tail of last page)
- `curl :8000/books/<unknown-uuid>/chunks` returns `404`
- `curl :8000/docs` shows OpenAPI UI with the three endpoints + their
  response schemas (`BookOut`, `BookList`, `ChunkPage`)
- Grep gate: `grep -r "fastapi\|pydantic" services/ db/` returns nothing
  (R3.2 — services and db stay FastAPI-free)
- Step 4 / V1 scripts still run unchanged:
  `uv run python scripts/store_pdf_inspect.py` → Hit@5 8/8, MRR 0.729;
  `uv run python scripts/probe_pgvector.py` → HNSW index usable, self-hit
- No upload, no file persistence, no background work, no status writes
  (all V3 scope)
