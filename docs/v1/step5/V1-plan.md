---
shaping: true
---

# Step 5: V1 Implementation Plan — Alembic + per-book store ops

Implements **V1** from [slices.md](./slices.md) — the Shape B parts **B3**
(Alembic adoption, three revisions) and **B4** (per-book `ingest_book` replacing
`load_book` / `TRUNCATE`). No FastAPI yet (V2) and no background ingest (V3).

Demo: `make db-migrate` against a fresh container leaves the DB at head with
CASCADE FKs + `books.status` / `books.error_message`. Re-running
`scripts/store_pdf_inspect.py` calls the new `ingest_book(conn, book_id, …)`
and prints the Step 3 parity report (Hit@5 8/8, MRR 0.729). A manually-inserted
sibling book row survives the re-run (no `TRUNCATE`).

## Files

| File                                       | Action                                                                                              |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `pyproject.toml`                           | Add `alembic` dependency                                                                            |
| `Makefile`                                 | Add `db-migrate` target                                                                             |
| `alembic.ini`                              | Create; `file_template` with timestamp, `sqlalchemy.url` placeholder                                |
| `alembic/env.py`                           | Create; read `DATABASE_URL` from env, rewrite scheme for psycopg3                                   |
| `alembic/script.py.mako`                   | Create (Alembic-generated template, untouched)                                                      |
| `alembic/versions/<ts>_<rev>_init.py`      | Create; body = `db/schema.sql` verbatim wrapped in `op.execute`                                     |
| `alembic/versions/<ts>_<rev>_chunks_cascade.py` | Create; drop + re-add `chunks.book_id` and `chunk_embeddings.chunk_id` FKs with `ON DELETE CASCADE` |
| `alembic/versions/<ts>_<rev>_book_status.py` | Create; `CREATE TYPE book_status`, `ALTER TABLE books ADD COLUMN status`, `error_message`           |
| `db/connection.py`                         | Modify — **remove** `init_db()`; keep `get_connection()`                                            |
| `services/store.py`                        | Replace `load_book` with `ingest_book(conn, book_id, …)` — no `TRUNCATE`                            |
| `scripts/store_pdf_inspect.py`             | Update — drop `init_db()`; call `ingest_book(conn, BOOK_ID, …)` with a fixed UUID                   |
| `scripts/probe_pgvector.py`                | Update — drop `init_db()` call                                                                      |

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
    "alembic>=1.13",
]
```

`alembic` pulls SQLAlchemy in as a transitive dep — used only by `env.py` to
acquire a connection. Revisions themselves use `op.execute(...)` with raw SQL;
no ORM models are introduced. Run `uv sync` after editing.

---

## 2. `Makefile` — `db-migrate` target

Append to the existing `Makefile`:

```makefile
.PHONY: db-up db-down db-logs db-shell db-reset db-status db-migrate

# ... existing targets ...

db-migrate:
	uv run alembic upgrade head
```

`uv run` ensures the project venv is used. Operator-driven setup — **not** wired
into FastAPI startup (R4.2, enforced in V2's lifespan).

---

## 3. `alembic.ini`

Create at repo root. Only the keys we actually use:

```ini
[alembic]
script_location = alembic
file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
prepend_sys_path = .
timezone = UTC

# Placeholder — alembic/env.py overrides from DATABASE_URL.
sqlalchemy.url = postgresql://placeholder

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
qualname =
[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = INFO
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

`file_template` matches the spike (shaping.md B3.1) — every revision file sorts
by creation time on disk, e.g. `2026_05_26_1430_a1b2c3_init.py`. `prepend_sys_path = .`
lets `env.py` import from the project root if ever needed.

---

## 4. `alembic/env.py`

```python
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

load_dotenv()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull DATABASE_URL from env; rewrite scheme so SQLAlchemy uses the psycopg3
# driver (already a project dep) instead of psycopg2.
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL missing — set in .env or environment")
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = None  # raw-SQL revisions; no ORM models


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

The scheme rewrite avoids adding `psycopg2-binary` just for Alembic. Everything
else is the stock template minus the SQLAlchemy-metadata wiring (we have none).

`alembic/script.py.mako` is whatever `alembic init` generates — leave it alone.

---

## 5. Revision: `<ts>_<rev>_init`

Generate with `uv run alembic revision -m "init"`; replace the body. `down_revision = None`
(this is the root).

```python
"""init

Revision ID: <auto>
Revises:
Create Date: <auto>
"""
from alembic import op

revision = "<auto>"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA_SQL = """
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
  token_count   INT,
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id        UUID PRIMARY KEY REFERENCES chunks(id),
  embedding       vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx
  ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
"""


def upgrade() -> None:
    op.execute(SCHEMA_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunk_embedding_idx")
    op.execute("DROP TABLE IF EXISTS chunk_embeddings")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS books")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

Body = `db/schema.sql` verbatim. `IF NOT EXISTS` is preserved so the revision
is safe against a Step-4 DB that already has the schema (relevant for the
`alembic stamp` migration path below).

**Existing-DB path (Step 4 → Step 5):** any DB that already has the Step-4
schema applied gets `uv run alembic stamp <init-rev>` once — Alembic records the
revision without re-running the DDL. New DBs just run `uv run alembic upgrade head`.

---

## 6. Revision: `<ts>_<rev>_chunks_cascade`

Generate with `uv run alembic revision -m "chunks_cascade"`; set `down_revision`
to the `_init` rev.

```python
"""chunks_cascade

Revision ID: <auto>
Revises: <init-rev>
Create Date: <auto>
"""
from alembic import op

revision = "<auto>"
down_revision = "<init-rev>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default PG-named FK constraints: <table>_<col>_fkey
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_book_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_book_id_fkey "
        "FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE chunk_embeddings DROP CONSTRAINT chunk_embeddings_chunk_id_fkey")
    op.execute(
        "ALTER TABLE chunk_embeddings ADD CONSTRAINT chunk_embeddings_chunk_id_fkey "
        "FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunk_embeddings DROP CONSTRAINT chunk_embeddings_chunk_id_fkey")
    op.execute(
        "ALTER TABLE chunk_embeddings ADD CONSTRAINT chunk_embeddings_chunk_id_fkey "
        "FOREIGN KEY (chunk_id) REFERENCES chunks(id)"
    )
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_book_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_book_id_fkey "
        "FOREIGN KEY (book_id) REFERENCES books(id)"
    )
```

Enables the V3 re-ingest path: `DELETE FROM chunks WHERE book_id=?` cascades to
`chunk_embeddings` in one statement (R5.2, R6.2). Verify constraint names
against `\d chunks` / `\d chunk_embeddings` in `make db-shell` first — Postgres
auto-naming is `<table>_<col>_fkey` but rename if a Step-4 DB diverges.

---

## 7. Revision: `<ts>_<rev>_book_status`

Generate with `uv run alembic revision -m "book_status"`; set `down_revision`
to the `_chunks_cascade` rev.

```python
"""book_status

Revision ID: <auto>
Revises: <chunks-cascade-rev>
Create Date: <auto>
"""
from alembic import op

revision = "<auto>"
down_revision = "<chunks-cascade-rev>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE book_status AS ENUM ('pending', 'processing', 'ready', 'failed')")
    op.execute(
        "ALTER TABLE books "
        "ADD COLUMN status book_status NOT NULL DEFAULT 'pending', "
        "ADD COLUMN error_message TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE books DROP COLUMN error_message")
    op.execute("ALTER TABLE books DROP COLUMN status")
    op.execute("DROP TYPE book_status")
```

`DEFAULT 'pending'` covers both new rows (V3 inserts at `pending`) and the
Step-4 book row carried over by `alembic stamp` (lands at `pending` on
revision-apply; V1's `ingest_book` does not touch status — see §9).

---

## 8. `db/connection.py` — remove `init_db()`

```python
import os

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing — set in .env or environment")
    return url


def get_connection() -> psycopg.Connection:
    """Open a connection with the pgvector type adapter registered.

    V2 adds get_pool() alongside this for FastAPI handlers; scripts keep using
    get_connection() (single conn, no pool).
    """
    conn = psycopg.connect(_database_url())
    register_vector(conn)
    return conn
```

Drops `init_db()` and the `_SCHEMA_PATH` constant — Alembic owns schema now
(R4.2 / B3.5). `db/schema.sql` stays in the repo as the verbatim source for the
`_init` revision; **do not edit it directly** (Step 6 Hand-off).

---

## 9. `services/store.py` — `ingest_book` replaces `load_book`

```python
import uuid

import numpy as np
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


def ingest_book(
    conn: psycopg.Connection,
    book_id: uuid.UUID,
    chunks: list[Chunk],
    embeddings: list[Embedding],
    title: str,
    file_path: str,
) -> uuid.UUID:
    """Per-book ingest. Single transaction:
      1. UPSERT books row (id-keyed)
      2. DELETE FROM chunks WHERE book_id = ?  (CASCADEs chunk_embeddings)
      3. INSERT chunks + chunk_embeddings for this book

    Idempotent per book_id. Does NOT touch other books' rows. Does NOT write
    books.status — V3's orchestrator owns the pending/processing/ready/failed
    lifecycle; V1 callers leave status at its default ('pending').
    """
    _assert_index_parity(chunks, embeddings)
    id_by_index = {c["chunk_index"]: uuid.uuid4() for c in chunks}

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO books (id, title, file_path) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, "
            "file_path = EXCLUDED.file_path",
            (book_id, title, file_path),
        )
        # CASCADE FK (rev _chunks_cascade) removes chunk_embeddings rows.
        cur.execute("DELETE FROM chunks WHERE book_id = %s", (book_id,))
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
                (
                    id_by_index[e["chunk_index"]],
                    np.asarray(e["vector"], dtype=np.float32),
                    e["embedding_model"],
                )
                for e in embeddings
            ],
        )
    conn.commit()
    return book_id
```

Changes vs `load_book`:

- **`book_id` is an arg** (not minted inside). Caller controls identity →
  re-ingest of the same book is just calling `ingest_book` again with the same
  id. V3's upload handler mints uuid4 on first upload; the Step 4 parity script
  hard-codes a constant (§10) so re-running stays idempotent.
- **`TRUNCATE` removed.** `INSERT … ON CONFLICT (id) DO UPDATE` for the book row,
  then `DELETE FROM chunks WHERE book_id = ?` (CASCADE handles
  `chunk_embeddings`) — other books untouched (R6.1).
- **`status` untouched.** Defaults to `'pending'` on first insert, preserved on
  re-ingest. V3's orchestrator wraps `ingest_book` with
  `UPDATE books SET status='processing' / 'ready' / 'failed'`.

---

## 10. `scripts/store_pdf_inspect.py` — fixed `book_id`, no `init_db()`

```python
"""Step 4 debug, V1-flavoured: load via ingest_book (fixed book_id), parity-check."""
import json
import uuid
from functools import partial
from pathlib import Path

from db.connection import get_connection
from services.chunker import load_chunks
from services.embeddings import load_embeddings
from services.eval import print_report, retrieve, run_eval
from services.retrieval import retrieve_pg
from services.store import ingest_book

CHUNKS_PATH = "temp/chunks.json"
EMBEDDINGS_PATH = "temp/embeddings.json"
EVAL_CASES_PATH = "eval/cases.json"
BOOK_TITLE = "AI Engineering: Building Applications with Foundation Models"
BOOK_FILE = "temp/books/AI_ENGINEERING_BUILDING.pdf"
# Fixed UUID → re-running this script re-ingests the same book row.
BOOK_ID = uuid.UUID("00000000-0000-0000-0000-00000000a1e0")


def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)
    embeddings = load_embeddings(EMBEDDINGS_PATH)
    cases = json.loads(Path(EVAL_CASES_PATH).read_text())

    with get_connection() as conn:
        book_id = ingest_book(conn, BOOK_ID, chunks, embeddings, BOOK_TITLE, BOOK_FILE)
        counts = {}
        for t in ("books", "chunks", "chunk_embeddings"):
            row = conn.execute(f"SELECT count(*) FROM {t}").fetchone()
            assert row is not None
            counts[t] = row[0]
        print(f"ingested book {book_id}: {counts}")

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

Changes:
- `init_db` removed from imports / call. Operator runs `make db-migrate` first.
- `load_book` → `ingest_book`; constant `BOOK_ID` passed in.
- `counts` query against `books` is now ≥1 (multi-book), not `==1`. The print
  still works; if a sibling row was inserted manually before the re-run, the
  count reflects that — which is the per-book-scoping check.

---

## 11. `scripts/probe_pgvector.py` — drop `init_db()`

One-line edit. The probe doesn't depend on the project schema (uses a TEMP
table), so removing `init_db()` is safe as long as the `vector` extension has
already been created — which the `_init` revision does.

```python
from db.connection import get_connection  # was: get_connection, init_db
...
def main() -> None:
    # init_db()  ← removed; run `make db-migrate` first
    with get_connection() as conn:
        ...
```

Everything below `main()` is unchanged.

---

## Implementation Order

1. **Deps + Makefile** (§§1–2) → `uv sync`
2. **Alembic skeleton** (§§3–4): `uv run alembic init alembic`, then overwrite
   `alembic.ini` and `alembic/env.py` per §§3–4. Delete the placeholder
   `alembic/versions/*` that `alembic init` may create.
3. **Generate revisions** (§§5–7): `uv run alembic revision -m "init"`, then
   `_chunks_cascade`, then `_book_status` — each replaces the auto-generated
   stub with the bodies above. Verify `down_revision` chains link correctly.
4. **Apply against a fresh DB**: `make db-reset && make db-migrate`. Inspect
   via `make db-shell`: `\d books` shows `status book_status NOT NULL DEFAULT 'pending'`
   and `error_message text`; `\d chunks` and `\d chunk_embeddings` show their
   FKs as `ON DELETE CASCADE`.
5. **Existing-DB path** (separate test run): `make db-up` against a Step-4
   volume → `uv run alembic stamp <init-rev>` → `uv run alembic upgrade head`.
   Same `\d` output as step 4.
6. **`db/connection.py`** (§8) — drop `init_db`.
7. **`services/store.py`** (§9) — replace `load_book` with `ingest_book`.
8. **`scripts/probe_pgvector.py`** (§11) — drop `init_db` call; re-run to
   confirm probe still passes.
9. **`scripts/store_pdf_inspect.py`** (§10) — switch to `ingest_book(BOOK_ID, …)`;
   run end-to-end; eyeball parity against Step 3 baseline.
10. **Per-book scoping check**: in `make db-shell`,
    `INSERT INTO books (id, title) VALUES ('00000000-0000-0000-0000-0000000000bb', 'sibling');`
    re-run `store_pdf_inspect.py`; confirm the sibling row survives and the
    AI Engineering chunks were replaced (count unchanged at 1286).

---

## Done When

- `uv sync` installs `alembic`
- `make db-migrate` against a fresh container ends with three revisions applied;
  `\d books` shows `status` (enum) + `error_message`; `\d chunks` /
  `\d chunk_embeddings` show CASCADE FKs
- `alembic stamp <init>` + `alembic upgrade head` against a Step-4 volume yields
  the same schema without re-running the `_init` DDL
- Revision files in `alembic/versions/` sort by creation time (timestamp-prefixed
  filenames per `file_template`)
- `db/connection.py` has no `init_db()`; `db/schema.sql` left in place as the
  verbatim source for `_init`
- `services/store.py` has `ingest_book(conn, book_id, …)` (no `load_book`, no
  `TRUNCATE`); single-transaction `UPSERT books` + `DELETE chunks` + `INSERT`s
- `scripts/store_pdf_inspect.py` runs against the new function with a fixed
  `BOOK_ID`; DB-backed Hit@5 / MRR match the Step 3 baseline (8/8, 0.729) modulo
  HNSW noise
- Re-running the script does not duplicate rows; a sibling book row inserted
  manually between runs survives the second run
- `scripts/probe_pgvector.py` still passes (HNSW index usable, self-hit)
- No FastAPI / pool work introduced (V2 scope)
- No status writes from any V1 code path — the AI Engineering book sits at
  `status='pending'` after ingest (V3 will own the lifecycle)
