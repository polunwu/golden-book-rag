---
shaping: true
---

# Step 4: V1 Implementation Plan — Postgres + pgvector

Implements **Shape B** with schema **B2-C** (`books` / `chunks` / `chunk_embeddings`)
from [shaping.md](./shaping.md). One slice: stand up the DB, load the book, verify
SQL retrieval against the Step 3 eval baseline.

## Files

| File                              | Action                                                              |
| --------------------------------- | ------------------------------------------------------------------- |
| `pyproject.toml`                  | Add `psycopg[binary]`, `pgvector`; add `db` to wheel packages       |
| `docker-compose.yml`              | Create                                                              |
| `.env.example`                    | Add DB vars                                                         |
| `.env`                            | Add DB vars (local, not committed)                                  |
| `db/__init__.py`                  | Create (empty)                                                      |
| `db/schema.sql`                   | Create                                                              |
| `db/connection.py`                | Create                                                              |
| `services/store.py`               | Create — loader                                                     |
| `services/retrieval.py`           | Create — `retrieve_pg`                                              |
| `services/eval.py`                | Modify — `run_eval` takes a retriever; `retrieve` is context-first  |
| `scripts/probe_pgvector.py`       | Create (run once)                                                   |
| `scripts/store_pdf_inspect.py`    | Create                                                              |
| `scripts/embed_pdf_inspect.py`    | Modify — pass `partial(retrieve, embeddings)`                       |

---

## 1. Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    "pymupdf>=1.27.2.3",
    "google-genai>=1.0",
    "tenacity>=9.0",
    "python-dotenv>=1.0",
    "numpy>=2.0",
    "psycopg[binary]>=3.2",
    "pgvector>=0.3",
]
```

```toml
[tool.hatch.build.targets.wheel]
packages = ["services", "db"]
```

Adding `db` keeps `from db.connection import …` importable from `scripts/` (uv
installs the project editable on `uv sync`). Run `uv sync` after editing.

---

## 2. `docker-compose.yml` + `.env`

`docker-compose.yml` (repo root):

```yaml
services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-bookrag}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bookrag}
      POSTGRES_DB: ${POSTGRES_DB:-bookrag}
    ports:
      - "5432:5432"
    volumes:
      - bookrag_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-bookrag}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  bookrag_pgdata:
```

Compose auto-reads the repo-root `.env`. Schema is **not** auto-applied via
`/docker-entrypoint-initdb.d/` — `init_db()` owns it (explicit-setup pattern, see
shaping.md Step 5 Hand-off).

Append to `.env.example` (and to the local `.env`):

```text
POSTGRES_USER=bookrag
POSTGRES_PASSWORD=bookrag
POSTGRES_DB=bookrag
DATABASE_URL=postgresql://bookrag:bookrag@localhost:5432/bookrag
```

`.gitignore` already covers `.env` / `.env.*`. Bring up: `docker compose up -d`.

---

## 3. `db/schema.sql`

Plain DDL — kept copy-pasteable so it can become Alembic migration `0001` later
(shaping.md Step 5 Hand-off). Idempotent: every object uses `IF NOT EXISTS`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS books (
  id         UUID PRIMARY KEY,
  title      TEXT,
  file_path  TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
  id            UUID PRIMARY KEY,
  book_id       UUID REFERENCES books(id),
  text          TEXT NOT NULL,
  page_start    INT,
  page_end      INT,
  section_path  TEXT[],
  section_title TEXT,
  section_level INT,
  chunk_index   INT NOT NULL,
  token_count   INT,                       -- nullable; not populated in Step 4
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id        UUID PRIMARY KEY REFERENCES chunks(id),
  embedding       vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx
  ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
```

---

## 4. `db/connection.py`

```python
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing — set in .env or environment")
    return url


def init_db() -> None:
    """Apply db/schema.sql idempotently (extension, tables, HNSW index).

    Uses a raw connection: the pgvector adapter cannot be registered until the
    `vector` extension exists, which this function itself creates. Run once before
    get_connection(). Not wired into any app lifecycle (Step 5 Hand-off).
    """
    with psycopg.connect(_database_url()) as conn:
        conn.execute(_SCHEMA_PATH.read_text())
        # `with` commits + closes on clean exit


def get_connection() -> psycopg.Connection:
    """Open a connection with the pgvector type adapter registered.

    Single accessor for all DB access — Step 5 swaps this for a psycopg_pool pool
    without touching callers (shaping.md Step 5 Hand-off).
    """
    conn = psycopg.connect(_database_url())
    register_vector(conn)
    return conn
```

`conn.execute()` runs the whole multi-statement script (psycopg3 allows it when no
params are passed). `register_vector` requires the `vector` extension to already
exist — hence `init_db()` must run first.

---

## 5. `services/store.py` — loader

```python
import uuid

import psycopg

from services.chunker import Chunk
from services.embeddings import Embedding


def _assert_index_parity(chunks: list[Chunk], embeddings: list[Embedding]) -> None:
    cidx = {c["chunk_index"] for c in chunks}
    eidx = {e["chunk_index"] for e in embeddings}
    if cidx != eidx:
        raise ValueError(
            f"chunk_index mismatch — chunks-only={sorted(cidx - eidx)[:5]}, "
            f"embeddings-only={sorted(eidx - cidx)[:5]}"
        )


def load_book(
    conn: psycopg.Connection,
    chunks: list[Chunk],
    embeddings: list[Embedding],
    title: str,
    file_path: str,
) -> uuid.UUID:
    """Full refresh: truncate, then insert one book + all chunks + all embeddings.
    Idempotent — re-running fully replaces prior data."""
    _assert_index_parity(chunks, embeddings)

    book_id = uuid.uuid4()
    id_by_index = {c["chunk_index"]: uuid.uuid4() for c in chunks}

    with conn.cursor() as cur:
        # Single-book MVP: full wipe + reload. Step 5 (multi-book upload) MUST
        # replace this with per-book scoped ops — TRUNCATE destroys other books
        # and locks whole tables. See shaping.md Step 5 Hand-off.
        cur.execute("TRUNCATE books, chunks, chunk_embeddings CASCADE")
        cur.execute(
            "INSERT INTO books (id, title, file_path) VALUES (%s, %s, %s)",
            (book_id, title, file_path),
        )
        cur.executemany(
            "INSERT INTO chunks (id, book_id, text, page_start, page_end, "
            "section_path, section_title, section_level, chunk_index) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    id_by_index[c["chunk_index"]], book_id, c["text"],
                    c["page_start"], c["page_end"], c["section_path"],
                    c["section_title"], c["section_level"], c["chunk_index"],
                )
                for c in chunks
            ],
        )
        cur.executemany(
            "INSERT INTO chunk_embeddings (chunk_id, embedding, embedding_model) "
            "VALUES (%s, %s, %s)",
            [
                (id_by_index[e["chunk_index"]], e["vector"], e["embedding_model"])
                for e in embeddings
            ],
        )
    conn.commit()
    return book_id
```

`section_path` (`list[str]`) → `TEXT[]` and `e["vector"]` (`list[float]`) →
`vector(1536)` are adapted natively (the latter via `register_vector`). `token_count`
is omitted → defaults `NULL`. `executemany` is ample for 1286 rows.

---

## 6. `services/retrieval.py` — SQL retriever

```python
import psycopg


def retrieve_pg(
    conn: psycopg.Connection,
    query_vec: list[float],
    k: int = 5,
) -> list[int]:
    """Top-k chunk_index by cosine distance via pgvector. query_vec must be
    L2-normalized — embed_query already guarantees this."""
    rows = conn.execute(
        "SELECT c.chunk_index "
        "FROM chunk_embeddings ce "
        "JOIN chunks c ON c.id = ce.chunk_id "
        "ORDER BY ce.embedding <=> %s "
        "LIMIT %s",
        (query_vec, k),
    ).fetchall()
    return [r[0] for r in rows]
```

Context (`conn`) is the first arg, so `partial(retrieve_pg, conn)` yields a
`(query_vec, k) -> list[int]` retriever — the shape `run_eval` expects.

---

## 7. `services/eval.py` — retriever-agnostic `run_eval`

Two changes. **(a)** `retrieve` becomes context-first so `partial` binds it
symmetrically with `retrieve_pg`:

```python
from typing import Callable

Retriever = Callable[[list[float], int], list[int]]


def retrieve(
    embeddings: list[Embedding],          # was: query_vec first
    query_vec: list[float],
    k: int = 5,
) -> list[int]:
    q = np.asarray(query_vec, dtype=np.float32)
    mat = np.asarray([e["vector"] for e in embeddings], dtype=np.float32)
    scores = mat @ q
    top = np.argsort(-scores)[:k]
    return [embeddings[i]["chunk_index"] for i in top]
```

**(b)** `run_eval` takes a `retriever` instead of `embeddings`; it still needs
`chunks` for `resolve_expected`:

```python
def run_eval(
    cases: list[EvalCase],
    chunks: list[Chunk],
    retriever: Retriever,
    k: int = 5,
) -> EvalReport:
    case_results: list[CaseResult] = []
    for case in cases:
        oos = case.get("out_of_scope", False)
        if oos:
            expected: list[int] = []
        else:
            expected = resolve_expected(case, chunks)
            if not expected:
                raise ValueError(
                    f"case {case['id']} resolved to 0 chunks — "
                    f"check page range / section substring"
                )
        qv = embed_query(case["query"])
        top = retriever(qv, k)            # was: retrieve(qv, embeddings, k=k)
        ...
```

The rest of `run_eval` (hit/rank, aggregates) and `print_report` are unchanged.
Callers build the retriever: in-memory `partial(retrieve, embeddings)`, DB
`partial(retrieve_pg, conn)`.

---

## 8. `scripts/probe_pgvector.py` (run once)

Pre-flight check before bulk ingestion — analogous to `probe_gemini_batch.py`.
Confirms the extension, the `vector`/psycopg adapter, `<=>` ordering, and that the
`vector_cosine_ops` HNSW index is usable by the operator.

```python
"""Probe pgvector: extension, vector round-trip, <=> ordering, HNSW index usability."""
import random

from db.connection import get_connection, init_db
from services.embeddings import EMBEDDING_DIM


def _rand_vec() -> list[float]:
    return [random.gauss(0.0, 1.0) for _ in range(EMBEDDING_DIM)]


def main() -> None:
    init_db()
    with get_connection() as conn:
        ver = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        print(f"pgvector extension: {ver[0] if ver else 'MISSING'}")

        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TEMP TABLE _probe (id int, embedding vector({EMBEDDING_DIM}))"
            )
            cur.execute("CREATE INDEX ON _probe USING hnsw (embedding vector_cosine_ops)")
            rows = [(i, _rand_vec()) for i in range(200)]
            cur.executemany("INSERT INTO _probe VALUES (%s, %s)", rows)

            probe_id, probe_vec = rows[0]
            cur.execute("SET LOCAL enable_seqscan = off")
            plan = cur.execute(
                "EXPLAIN SELECT id FROM _probe ORDER BY embedding <=> %s LIMIT 5",
                (probe_vec,),
            ).fetchall()
            plan_text = "\n".join(r[0] for r in plan)
            print(f"HNSW index usable by <=>: {'hnsw' in plan_text.lower()}")

            top = cur.execute(
                "SELECT id FROM _probe ORDER BY embedding <=> %s LIMIT 5",
                (probe_vec,),
            ).fetchall()
            print(f"nearest to row {probe_id}: {[r[0] for r in top]}  "
                  f"(self-hit rank 1: {top[0][0] == probe_id})")


if __name__ == "__main__":
    main()
```

Success: extension prints a version, index is usable, the probe vector is its own
nearest neighbour. The TEMP table is dropped when the connection closes.

---

## 9. `scripts/store_pdf_inspect.py` — end-to-end + parity

```python
"""Step 4 debug: init DB, load book, eval via pgvector, compare to Step 3 baseline."""
import json
from functools import partial
from pathlib import Path

from db.connection import get_connection, init_db
from services.chunker import load_chunks
from services.embeddings import load_embeddings
from services.eval import print_report, retrieve, run_eval
from services.retrieval import retrieve_pg
from services.store import load_book

CHUNKS_PATH = "temp/chunks.json"
EMBEDDINGS_PATH = "temp/embeddings.json"
EVAL_CASES_PATH = "eval/cases.json"
BOOK_TITLE = "AI Engineering: Building Applications with Foundation Models"
BOOK_FILE = "temp/books/AI_ENGINEERING_BUILDING.pdf"


def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)
    embeddings = load_embeddings(EMBEDDINGS_PATH)
    cases = json.loads(Path(EVAL_CASES_PATH).read_text())

    init_db()
    with get_connection() as conn:
        book_id = load_book(conn, chunks, embeddings, BOOK_TITLE, BOOK_FILE)
        counts = {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("books", "chunks", "chunk_embeddings")
        }
        print(f"loaded book {book_id}: {counts}")

        report_pg = run_eval(cases, chunks, partial(retrieve_pg, conn), k=5)
        print("\n=== pgvector retrieval ===")
        print_report(report_pg)

    report_mem = run_eval(cases, chunks, partial(retrieve, embeddings), k=5)
    print("\n=== in-memory retrieval (parity reference) ===")
    print_report(report_mem)
    print("\nStep 3 baseline: Hit 8/8, Recall@5 0.590, MRR 0.729")


if __name__ == "__main__":
    main()
```

Prints DB-backed and in-memory reports side by side; they should agree (modulo HNSW
approximation, per shaping.md Fit Check notes).

---

## 10. `scripts/embed_pdf_inspect.py` — update for the new `run_eval`

`run_eval` no longer takes `embeddings`. Change the import and the call:

```python
from functools import partial
from services.eval import print_report, retrieve, run_eval
...
    report = run_eval(cases, chunks, partial(retrieve, embeddings), k=5)
```

Keeps the Step 3 script runnable after the `eval.py` refactor.

---

## Implementation Order

1. **Deps** (step 1) → `uv sync`
2. **`docker-compose.yml` + `.env`** (step 2) → `docker compose up -d`, wait for healthy
3. **`db/schema.sql` + `db/connection.py`** (steps 3–4)
4. **`scripts/probe_pgvector.py`** (step 8) → run, confirm extension + index usable
5. **`services/store.py`** (step 5)
6. **`services/retrieval.py` + `services/eval.py` refactor** (steps 6–7)
7. **`scripts/embed_pdf_inspect.py` update** (step 10) → Step 3 script still runs
8. **`scripts/store_pdf_inspect.py`** (step 9) → run end-to-end, eyeball parity

---

## Done When

- `uv sync` installs `psycopg[binary]` and `pgvector`
- `docker compose up -d` brings up Postgres; container reports healthy
- `DATABASE_URL` loaded from `.env`; a missing value raises a clear error
- `init_db()` creates `books` / `chunks` / `chunk_embeddings` + the HNSW index; re-running is a no-op
- `probe_pgvector.py` prints a pgvector version, `HNSW index usable: True`, and a self-hit
- `load_book` inserts 1 book, 1286 chunks, 1286 embeddings; re-running fully refreshes without duplicates/errors
- Loader raises if `chunks.json` / `embeddings.json` `chunk_index` sets differ
- `retrieve_pg` returns `list[chunk_index]`; `run_eval` runs against `partial(retrieve_pg, conn)`
- `store_pdf_inspect.py` prints pgvector and in-memory reports; DB-backed Hit@5 / MRR match the Step 3 baseline (8/8, 0.729), or diffs are explained by HNSW approximation
- `embed_pdf_inspect.py` still runs after the `eval.py` refactor
- No FastAPI / frontend work introduced
