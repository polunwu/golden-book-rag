---
shaping: true
---

# Step 6: V1 Implementation Plan — Book-scoped search

Implements **V1** from [slices.md](./slices.md) — all of Shape A: `search_chunks`
(A1), `embed_query` relocated to `services/embeddings.py` (A3), the
`POST /books/{id}/search` handler + gating (A4), schemas (A5), and the eval
rewire that deletes `retrieve_pg` (A2/A6).

Demo: `curl` a `ready` book's `/search` → ranked chunks with scores + citations;
`404`/`409`/`422` on the edges; `scripts/store_pdf_inspect.py` still prints the
Step 3 parity report, now through `search_chunks`.

No new deps, no migration — the schema is unchanged from Step 5.

## Files

| File                            | Action                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------- |
| `services/embeddings.py`        | Add `embed_query` (moved from `eval.py`)                                         |
| `services/eval.py`              | Drop `embed_query` def; re-import it; prune now-unused imports                   |
| `services/types.py`             | Create — shared `ChunkBase` (leaf module)                                       |
| `services/retrieval.py`         | Replace `retrieve_pg` with `search_chunks` + `ChunkHit` (extends `ChunkBase`)   |
| `api/schemas.py`                | Import `ChunkBase`; refactor `ChunkOut` onto it; add `SearchRequest`, `SearchHit`, `SearchResponse` |
| `api/routers/books.py`          | Add `POST /{book_id}/search` handler + imports                                  |
| `scripts/store_pdf_inspect.py`  | Rewire eval `Retriever` onto `search_chunks`; drop `retrieve_pg`                |
| `tests/conftest.py`             | Stub `api.routers.books.embed_query`                                            |
| `tests/test_search.py`          | Create                                                                          |

---

## 1. `services/embeddings.py` — add `embed_query`

`embed_query` already composes three functions that live here (`make_client`,
`embed_batch_call`, `l2_normalize`), so this is its natural home (A3). Append
after `l2_normalize` (it depends on all three):

```python
def embed_query(text: str) -> list[float]:
    """Embed a search query. RETRIEVAL_QUERY task type (asymmetric vs the
    RETRIEVAL_DOCUMENT chunks); L2-normalized so cosine distance == 1 - dot."""
    client = make_client()
    vec = embed_batch_call(client, [text], task_type="RETRIEVAL_QUERY")[0]
    return l2_normalize(vec)
```

Verbatim move from `services/eval.py:38` — no behavioral change.

---

## 2. `services/eval.py` — re-import, prune

`embed_query` was the only consumer of `make_client` / `embed_batch_call` in this
module. After the move, the import line narrows and the def is replaced by a
re-export so `run_eval` (line 100) and any external importer keep working.

```python
from typing import Callable, TypedDict

import numpy as np

from services.chunker import Chunk
from services.embeddings import Embedding, embed_query, l2_normalize  # noqa: F401

Retriever = Callable[[list[float], int], list[int]]
```

- Add `embed_query` to the import (re-export; `# noqa: F401` because it's used
  only by importers of `eval`, not within this file after the move — keep it so
  `from services.eval import embed_query` doesn't break).
- `l2_normalize` stays imported **only if** still used here — it is **not**
  (grep: `retrieve` uses `np` directly). Drop `l2_normalize` and `make_client`
  and `embed_batch_call`. Final import: `from services.embeddings import Embedding, embed_query`.
- **Delete** the `def embed_query(...)` block at lines 38–41.

Net `eval.py` import line:

```python
from services.embeddings import Embedding, embed_query  # embed_query re-exported
```

---

## 3a. `services/types.py` — shared `ChunkBase` (new file)

The 7 chunk fields live here once. It's a leaf module (only `pydantic`), so both
`services/retrieval.py` (`ChunkHit`) and `api/schemas.py` (`ChunkOut`,
`SearchHit`) can import it — dependency runs api → services, never the reverse.

```python
from pydantic import BaseModel


class ChunkBase(BaseModel):
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: list[str] | None
    section_title: str | None
    section_level: int | None
```

---

## 3. `services/retrieval.py` — `search_chunks` replaces `retrieve_pg`

Full file rewrite. `retrieve_pg` is deleted (A2); `search_chunks` is the single
pgvector retriever, book-scoped, returning rows rich enough for both the API
response (A4/N6) and the eval shim (A6).

`ChunkHit` reuses the shared `ChunkBase` (`services/types.py`, §3a) so the chunk
fields live in exactly one place — it only adds `distance`. The base sits in a
neutral module that both the service and `api.schemas` import, so the dependency
runs api → services, never the reverse.

```python
from uuid import UUID

import numpy as np
import psycopg
from psycopg.rows import dict_row

from services.types import ChunkBase


class ChunkHit(ChunkBase):
    distance: float


def search_chunks(
    conn: psycopg.Connection,
    book_id: UUID,
    query_vec: list[float],
    k: int = 5,
) -> list[ChunkHit]:
    """Top-k chunks for one book by pgvector cosine distance (`<=>`), HNSW.

    query_vec must be L2-normalized (embed_query guarantees this). Uses its own
    dict_row cursor so it works under both the pooled dict_row connection (API)
    and a plain get_connection() (scripts) — independent of the connection's
    default row_factory.
    """
    # pgvector's psycopg adapter dumps numpy.ndarray as a vector literal; a
    # plain list[float] would silently go out as float8[] and break `<=>`.
    qv = np.asarray(query_vec, dtype=np.float32)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT c.chunk_index, c.text, c.page_start, c.page_end, "
            "c.section_path, c.section_title, c.section_level, "
            "ce.embedding <=> %s AS distance "
            "FROM chunk_embeddings ce "
            "JOIN chunks c ON c.id = ce.chunk_id "
            "WHERE c.book_id = %s "
            "ORDER BY ce.embedding <=> %s "
            "LIMIT %s",
            (qv, book_id, qv, k),
        ).fetchall()
    # dict_row keys match ChunkHit's fields 1:1; model_validate coerces
    # distance to float — no manual field listing.
    return [ChunkHit.model_validate(r) for r in rows]
```

Notes:
- `qv` is passed **twice** — once for the `distance` projection, once for the
  `ORDER BY`. Ordering by the bare `ce.embedding <=> %s` expression (not the
  `distance` alias) keeps the HNSW index in play; verify with `EXPLAIN` that an
  Index Scan on `chunk_embedding_idx` is chosen (auto-named HNSW indexes don't
  show "hnsw" in the plan — confirm by the index name + Index Scan).
- `WHERE c.book_id = %s` is the new scoping (R3.1) absent from `retrieve_pg`.
- `distance` is cosine distance ∈ [0,2]; the handler converts to
  `score = 1 - distance` (A4/N6).

---

## 4. `api/schemas.py` — search models

Add after `UploadBookForm`. Needs `Field` + `field_validator`, plus the shared
base from `services.types`:

```python
from pydantic import BaseModel, Field, field_validator

from services.types import ChunkBase
```

Also refactor the existing `ChunkOut` onto the shared `ChunkBase` (§3a) so the 7
chunk fields are defined once and reused by `ChunkOut` (browse), `SearchHit`
(search out), and `ChunkHit` (retrieval layer, §3):

```python
class ChunkOut(ChunkBase):
    pass
```

The search models (`ChunkOut`/`ChunkPage` keep their current position):

```python
class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v


class SearchHit(ChunkBase):
    score: float


class SearchResponse(BaseModel):
    book_id: UUID
    query: str
    k: int
    hits: list[SearchHit]
```

`min_length=1` rejects `""`; the validator rejects whitespace-only — both
surface as `422` (mirrors the upload handler's explicit title check). `k`
bounds `[1,20]` per R1.1.

---

## 5. `api/routers/books.py` — `POST /{book_id}/search`

Add imports:

```python
from api.schemas import (
    BookList, BookOut, ChunkOut, ChunkPage, SearchHit, SearchRequest,
    SearchResponse, UploadBookForm, UploadResponse,
)
from services.embeddings import embed_query
from services.retrieval import search_chunks
```

Add the handler (place after `get_chunks`, before `delete_book` — keeps the
read-ish routes together):

```python
@router.post("/{book_id}/search", response_model=SearchResponse)
def search_book(
    book_id: UUID,
    body: SearchRequest,
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> SearchResponse:
    row = conn.execute(
        "SELECT status FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")
    if row["status"] != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"book not ready for search (status={row['status']})",
        )

    query_vec = embed_query(body.query)
    hits = search_chunks(conn, book_id, query_vec, body.k)
    return SearchResponse(
        book_id=book_id,
        query=body.query,
        k=body.k,
        hits=[
            # h shares ChunkBase with SearchHit; drop distance, derive score.
            SearchHit(**h.model_dump(exclude={"distance"}), score=1.0 - h.distance)
            for h in hits
        ],
    )
```

- Status gate before any embedding work — a non-`ready` book costs no Gemini
  call (R2.2). `404` vs `409` distinguishes "no such book" from "not ready yet".
- `conn` is the pooled `dict_row` connection (R4.3); `row["status"]` is the enum
  value as a string.
- Route `/{book_id}/search` (POST) doesn't collide with `/{book_id}` (GET) or
  `/upload` (POST).

---

## 6. `scripts/store_pdf_inspect.py` — rewire eval onto `search_chunks`

Swap the `retrieve_pg` import + `partial` for a `chunk_index` shim over
`search_chunks` scoped to the script's fixed `BOOK_ID` (A6). `search_chunks`
sets its own `dict_row` cursor, so it works fine over the script's plain
`get_connection()`.

Import change:

```python
from services.retrieval import search_chunks  # was: retrieve_pg
```

Inside `main()`, replace the `report_pg` line:

```python
    with get_connection() as conn:
        book_id = ingest_book(conn, BOOK_ID, chunks, embeddings, BOOK_TITLE, BOOK_FILE)
        counts = {}
        for t in ("books", "chunks", "chunk_embeddings"):
            row = conn.execute(f"SELECT count(*) FROM {t}").fetchone()
            assert row is not None
            counts[t] = row[0]
        print(f"ingested book {book_id}: {counts}")

        def pg_retriever(qv: list[float], k: int) -> list[int]:
            return [h.chunk_index for h in search_chunks(conn, BOOK_ID, qv, k)]

        report_pg = run_eval(cases, chunks, pg_retriever, k=5)
        print("\n=== pgvector retrieval ===")
        print_report(report_pg)
```

Everything else unchanged. The shim returns `list[int]` — the `Retriever`
contract `run_eval` expects — so the parity numbers are unaffected (R5.1). It
also fixes the old all-books fragility: the eval now scopes to `BOOK_ID`.

---

## 7. `tests/conftest.py` — stub `embed_query`

The search handler calls the real `embed_query` (Gemini) unless stubbed. Add a
deterministic stub matching the existing `_fake_embed_chunks` scheme so a query
embedding equals chunk_index 0's stored vector → chunk_index 0 is the top hit.

Add near `_fake_embed_chunks`:

```python
def _fake_embed_query(text: str) -> list[float]:
    # Matches _fake_embed_chunks' rng(chunk_index=0) → top hit is chunk_index 0.
    rng = np.random.default_rng(0)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()
```

Extend the autouse `_no_gemini` fixture to also patch the handler's reference:

```python
@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.ingest as ingest_mod
    import api.routers.books as books_mod
    monkeypatch.setattr(ingest_mod, "embed_chunks", _fake_embed_chunks)
    monkeypatch.setattr(books_mod, "embed_query", _fake_embed_query)
```

`books_mod.embed_query` is the name bound by `from services.embeddings import
embed_query` in the router — patching it there intercepts the handler's call.

---

## 8. `tests/test_search.py` — create

```python
"""POST /books/{id}/search — gating + ranked retrieval.

Gemini is stubbed (conftest._no_gemini): _fake_embed_query == chunk_index 0's
stored vector, so chunk_index 0 is the deterministic top hit.
"""
from __future__ import annotations

import uuid

from tests._helpers import make_pdf_bytes, upload


def _ready_book(client, book_ids, *, title="searchable") -> uuid.UUID:
    resp = upload(client, book_ids, content=make_pdf_bytes(title), title=title)
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "ready"
    return bid


# --- gating -------------------------------------------------------------

def test_search_unknown_book_404(client):
    resp = client.post(f"/books/{uuid.uuid4()}/search", json={"query": "x"})
    assert resp.status_code == 404


def test_search_not_ready_409(client, book_ids):
    # zero-byte PDF → background ingest lands at 'failed' (non-ready)
    resp = upload(client, book_ids, content=b"", title="broken")
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "failed"

    resp = client.post(f"/books/{bid}/search", json={"query": "x"})
    assert resp.status_code == 409
    assert "status=failed" in resp.json()["detail"]


def test_search_empty_query_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/search", json={"query": ""}).status_code == 422
    assert client.post(f"/books/{bid}/search", json={"query": "   "}).status_code == 422


def test_search_k_out_of_range_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/search", json={"query": "x", "k": 0}).status_code == 422
    assert client.post(f"/books/{bid}/search", json={"query": "x", "k": 21}).status_code == 422


# --- happy path ---------------------------------------------------------

def test_search_happy_path_ranked(client, book_ids):
    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/search", json={"query": "anything", "k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == str(bid)
    assert body["k"] == 5
    hits = body["hits"]
    assert 1 <= len(hits) <= 5
    # deterministic stub → chunk_index 0 is the nearest
    assert hits[0]["chunk_index"] == 0
    # scores are descending and carry citation metadata
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert "text" in hits[0] and "page_start" in hits[0]


# --- scoping ------------------------------------------------------------

def test_search_scoped_to_book(client, book_ids):
    a = _ready_book(client, book_ids, title="book A")
    _ready_book(client, book_ids, title="book B")  # noise — must not leak in

    a_total = client.get(f"/books/{a}/chunks").json()["total"]
    resp = client.post(f"/books/{a}/search", json={"query": "x", "k": 200})
    assert resp.status_code == 200
    # k=200 ≫ chunk count → returns exactly book A's chunks, never book B's
    assert len(resp.json()["hits"]) == a_total
```

---

## Implementation Order

1. **`services/embeddings.py`** (§1) — add `embed_query`.
2. **`services/eval.py`** (§2) — drop the def, re-import, prune. Run
   `python -c "from services.eval import embed_query"` to confirm the re-export.
3. **`services/retrieval.py`** (§3) — replace `retrieve_pg` with `search_chunks`.
4. **`scripts/store_pdf_inspect.py`** (§6) — rewire; run it: parity report must
   match Step 3 baseline (Hit@5 8/8, MRR 0.729). Confirms A1+A6 before any API.
5. **`EXPLAIN` check** — in `make db-shell`, `EXPLAIN` the `search_chunks` query
   with a `book_id` filter; confirm Index Scan on `chunk_embedding_idx`.
6. **`api/schemas.py`** (§4) — add the three models.
7. **`api/routers/books.py`** (§5) — add the handler + imports.
8. **`tests/conftest.py`** + **`tests/test_search.py`** (§§7–8) — `pytest`.
9. **Manual `curl` smoke** — boot `uvicorn`, upload a real book to `ready`,
   `curl` the four cases (200/404/409/422).
10. **Boundary grep** — `grep -rn "fastapi" services/ db/` returns nothing (R4.2).

---

## Done When

- `from services.eval import embed_query` still resolves; `embed_query` defined
  in `services/embeddings.py`; no behavioral change in `run_eval`
- `services/retrieval.py` exposes `search_chunks` (book-scoped, rich rows) and
  no longer defines `retrieve_pg`; nothing imports `retrieve_pg`
- `EXPLAIN` shows the search query using the HNSW index (Index Scan on
  `chunk_embedding_idx`), filtered by `book_id`
- `POST /books/{id}/search` on a `ready` book: `200`, ≤`k` hits, descending
  `score`, each with text + page/section citation
- `404` unknown id; `409` for `pending`/`processing`/`failed` (detail names the
  status); `422` for blank `query` or `k ∉ [1,20]`
- Scoping: `k=200` on book A returns exactly book A's chunk count, never B's
- `scripts/store_pdf_inspect.py` runs through `search_chunks` and prints the
  Step 3 parity report (R5.1)
- `pytest` green; `grep` finds no FastAPI import in `services/` or `db/` (R4.2)
- No LLM, no cross-book search, no rerank introduced (Step 7+ scope)
