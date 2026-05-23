---
shaping: true
---

# Step 4: Postgres + pgvector — Shaping

Step 3 produced `temp/embeddings.json` (1286 L2-normalized 1536-dim vectors) and a
reusable eval harness in `services/eval.py`. Step 4 moves retrieval off in-memory
numpy and into Postgres + pgvector, and proves it with the same eval cases.

## Requirements (R)

| ID       | Requirement                                                                                                                                  | Status     |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| R0       | Stand up Postgres + pgvector locally, load `temp/embeddings.json`, and run cosine similarity search through SQL                              | Core goal  |
| R1       | Postgres runs reproducibly from committed config — single documented command, no manual install/build; pgvector extension enabled            | Must-have  |
| **R2**   | **Schema**                                                                                                                                   | Must-have  |
| R2.1     | Persists what retrieval needs: `chunk_index`, `embedding vector(1536)`, `embedding_model`                                                     | Must-have  |
| R2.2     | 🟡 Full `books` / `chunks` / `chunk_embeddings` design from the architecture doc, so Step 5's upload API extends it without schema migration  | Must-have  |
| R3       | HNSW ANN index on the embedding column using `vector_cosine_ops`                                                                             | Must-have  |
| R4       | Load is idempotent — re-running from `temp/embeddings.json` fully refreshes without duplicates/errors; loader asserts the embeddings and chunks files cover the same `chunk_index` set | Must-have  |
| R5       | SQL-backed retriever: embed query → `ORDER BY embedding <=> $1 LIMIT k` → returns `list[chunk_index]`, drop-in compatible with the eval harness | Must-have  |
| R6       | Existing `run_eval` runs against the SQL retriever; metrics are compared to the Step 3 in-memory baseline (Hit@5 8/8, MRR 0.729) to confirm parity | Must-have  |
| R7       | DB connection config read from env (`DATABASE_URL` in `.env`), never committed; clear error if missing                                       | Must-have  |
| R8       | Step 4 stays independent from FastAPI / frontend; services and scripts remain runnable standalone                                            | Must-have  |

## A: Array column + Python-side distance (rejected)

| Part | Mechanism                                                                                              | Flag |
| ---- | ------------------------------------------------------------------------------------------------------ | :--: |
| A1   | Store each embedding as a plain `double precision[]` (or `jsonb`) column in an `embeddings` table      |      |
| A2   | Retrieval fetches all rows, rebuilds the matrix, computes cosine in Python with numpy                  |      |
| A3   | No pgvector extension, no vector index                                                                 |      |

Fails R0 (similarity search never happens in SQL — this is Step 3's numpy `retrieve`
with a database bolted on, and the DB earns nothing), R3 (no ANN index possible on an
array column), and R5 (the retriever is not a SQL `<=>` query).

## B: Dockerized pgvector + SQL retriever wired into the eval harness

| Part   | Mechanism                                                                                                                                                                       | Flag |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| **B1** | **Dockerized Postgres + pgvector**                                                                                                                                              |      |
| B1.1   | `docker-compose.yml` at repo root using image `pgvector/pgvector:pg17`; named volume for data; `POSTGRES_USER/PASSWORD/DB` from `.env`                                          |      |
| B1.2   | Documented bring-up command (`docker compose up -d`); `.env.example` records the `DATABASE_URL` shape                                                                            |      |
| **B2** | 🟡 **Schema — `books` / `chunks` / `chunk_embeddings`** (B2-C, selected; DDL below)                                                                                              |      |
| **B3** | **DB access layer** `db/connection.py`                                                                                                                                          |      |
| B3.1   | psycopg3 connection built from `DATABASE_URL`; raise clear error if env missing                                                                                                 |      |
| B3.2   | Register pgvector type adapter (`pgvector.psycopg.register_vector`) on each connection                                                                                          |      |
| B3.3   | `init_db()` applies `db/schema.sql` idempotently (`CREATE EXTENSION IF NOT EXISTS vector`, `CREATE TABLE IF NOT EXISTS …`, `CREATE INDEX IF NOT EXISTS …`)                       |      |
| **B4** | 🟡 **Idempotent loader** `services/store.py`                                                                                                                                    |      |
| B4.1   | Load `temp/embeddings.json` + `temp/chunks.json`; assert both files cover the same `chunk_index` set, else raise                                                                |      |
| B4.2   | 🟡 `TRUNCATE books, chunks, chunk_embeddings CASCADE` first; insert one `books` row for the source PDF; insert `chunks` with generated UUIDs, building a `chunk_index → id` map; insert `chunk_embeddings` keyed by that map | |
| B4.3   | 🟡 Bulk insert via psycopg `executemany` (ample for 1286 rows); HNSW index already exists from `schema.sql` / `init_db()`                                                       |      |
| **B5** | **SQL retriever** `services/retrieval.py`                                                                                                                                       |      |
| B5.1   | 🟡 `retrieve_pg(conn, query_vec, k=5) -> list[int]`: `SELECT c.chunk_index FROM chunk_embeddings ce JOIN chunks c ON c.id = ce.chunk_id ORDER BY ce.embedding <=> %s LIMIT %s`   |      |
| B5.2   | Reuses `embed_query` from `services/eval.py` (`task_type="RETRIEVAL_QUERY"`, L2-normalized) — no new embedding path                                                             |      |
| **B6** | **Retriever-agnostic eval harness**                                                                                                                                             |      |
| B6.1   | Refactor `run_eval` to take a `retriever: Callable[[list[float], int], list[int]]` instead of hardcoding the numpy `retrieve`                                                    |      |
| B6.2   | In-memory path becomes `partial(retrieve, embeddings)`; DB path is `retrieve_pg` bound to a connection — both plug into the same `run_eval`                                      |      |
| **B7** | **Probe + debug scripts**                                                                                                                                                       |      |
| B7.1   | `scripts/probe_pgvector.py`: insert a sample vector, round-trip it, confirm `<=>` ordering and that the HNSW index is used (`EXPLAIN`) — analogous to `probe_gemini_batch.py`    |      |
| B7.2   | `scripts/store_pdf_inspect.py`: `init_db` → load → `run_eval(retriever=retrieve_pg)` → `print_report`; print the Step 3 in-memory baseline alongside for the parity check (R6)   |      |

**Environment note:** `docker-compose.yml` is a local-dev tool only. Production points
`DATABASE_URL` at a managed pgvector-capable Postgres (Supabase / Neon / RDS / Cloud
SQL) — the same code runs against both, only the env var differs (R7). Deployment
itself is out of Step 4 scope.

## B2: Schema scope (decided → B2-C)

The three alternatives differed only in how many tables Step 4 creates; all other
parts of Shape B are identical. **B2-C selected** — it satisfies R2.2 (the schema is
the architecture-doc design Step 5 extends without migration).

**B2-A — `chunk_embeddings` only** *(rejected)*. Vectors in the DB; chunk metadata
stays in `temp/chunks.json`. Leaves a permanent vectors-in-DB / metadata-in-JSON
split and the SQL retriever cannot return page/section. Fails R2.2.

**B2-B — `chunks` + `chunk_embeddings`** *(rejected)*. DB self-contained, but no
`books` table — Step 5 would still need a migration to add it. Fails R2.2.

**B2-C — `books` + `chunks` + `chunk_embeddings`** *(selected)*. Full architecture-doc
schema with UUID ids and a `book_id` FK; loader inserts a `books` row for the source
PDF. `chunk_index` remains an `INT` column on `chunks`, so the eval harness keeps its
existing key.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE books (
  id         UUID PRIMARY KEY,
  title      TEXT,
  file_path  TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chunks (
  id            UUID PRIMARY KEY,
  book_id       UUID REFERENCES books(id),
  text          TEXT NOT NULL,
  page_start    INT,
  page_end      INT,
  section_path  TEXT[],
  section_title TEXT,
  section_level INT,
  chunk_index   INT NOT NULL,
  token_count   INT,                       -- nullable; no consumer in Step 4
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chunk_embeddings (
  chunk_id        UUID PRIMARY KEY REFERENCES chunks(id),
  embedding       vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx
  ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
```

| Req  | Requirement                                                          | Status    | B2-A | B2-B | B2-C |
| ---- | -------------------------------------------------------------------- | --------- | ---- | ---- | ---- |
| R0   | Postgres + pgvector, load embeddings, similarity search via SQL      | Core goal | ✅   | ✅   | ✅   |
| R2.1 | Persists chunk_index, vector(1536), embedding_model                  | Must-have | ✅   | ✅   | ✅   |
| R2.2 | 🟡 Full books / chunks / chunk_embeddings architecture-doc design    | Must-have | ❌   | ❌   | ✅   |
| R4   | Idempotent load with chunk_index parity assertion                    | Must-have | ✅   | ✅   | ✅   |
| R5   | SQL retriever returns `list[chunk_index]`                            | Must-have | ✅   | ✅   | ✅   |
| R6   | `run_eval` against SQL retriever; parity vs Step 3 baseline          | Must-have | ✅   | ✅   | ✅   |

**Notes:**

- B2-A fails R2.2: a `chunk_embeddings`-only table is not the architecture schema.
- B2-B fails R2.2: no `books` table — Step 5 would re-migrate to add one.

## Fit Check

| Req  | Requirement                                                                       | Status    | A   | B   |
| ---- | --------------------------------------------------------------------------------- | --------- | --- | --- |
| R0   | Postgres + pgvector, load embeddings, similarity search via SQL                   | Core goal | ❌  | ✅  |
| R1   | Reproducible Postgres from committed config; pgvector enabled                     | Must-have | ✅  | ✅  |
| R2.1 | Schema persists chunk_index, vector(1536), embedding_model                        | Must-have | ❌  | ✅  |
| R2.2 | 🟡 Full books / chunks / chunk_embeddings architecture-doc design                 | Must-have | ❌  | ✅  |
| R3   | HNSW ANN index (`vector_cosine_ops`)                                              | Must-have | ❌  | ✅  |
| R4   | Idempotent load with chunk_index parity assertion                                 | Must-have | ✅  | ✅  |
| R5   | SQL-backed retriever drop-in for the eval harness                                 | Must-have | ❌  | ✅  |
| R6   | `run_eval` against SQL retriever; parity vs Step 3 baseline                       | Must-have | ✅  | ✅  |
| R7   | Connection config from `.env`, never committed                                   | Must-have | ✅  | ✅  |
| R8   | Independent from FastAPI / frontend                                               | Must-have | ✅  | ✅  |

**Notes:**

- A fails R0/R2.1/R2.2/R3/R5: an array column with Python-side distance never searches
  in SQL, cannot carry a `vector` type, ANN index, or the architecture schema, and the
  retriever is not a `<=>` query — the database adds nothing over Step 3.
- HNSW is approximate. With only 1286 rows the planner may seq-scan anyway; if it does
  use the index, a rank could shift slightly. R6's parity check tolerates that: compare
  DB metrics to the in-memory baseline and explain any HNSW-induced diff.
- Step 3 vectors are L2-normalized, so cosine distance `<=>` ranks identically to the
  in-memory dot-product `retrieve` — this is what R6 parity rests on. `<=>` is kept
  (over the equivalent `<#>` inner product) because it stays correct under float32
  norm drift, and its opclass `vector_cosine_ops` matches the B5.1 query operator.

## Selected Shape

**B: Dockerized pgvector + SQL retriever wired into the eval harness**, with schema
**B2-C** (`books` / `chunks` / `chunk_embeddings`). No flagged unknowns remain.

## Slice

### Slice 1: Stand up the DB and verify SQL retrieval

Input:

- `temp/chunks.json`, `temp/embeddings.json` (from Steps 2–3)
- `DATABASE_URL` in `.env`; Docker available

Output:

- Running Postgres + pgvector container with `books` / `chunks` / `chunk_embeddings`
  populated (1 book, 1286 chunks, 1286 embeddings) and an HNSW index
- Printed eval report from `run_eval(retriever=retrieve_pg)` next to the Step 3
  in-memory baseline

Done when:

- `docker compose up -d` brings up Postgres with the pgvector extension enabled
- `init_db()` creates `books` / `chunks` / `chunk_embeddings` + the HNSW index idempotently
- Loader inserts 1 book, 1286 chunks, 1286 embeddings; re-running fully refreshes
  without duplicates or errors
- Loader raises if the `chunk_index` sets of `chunks.json` and `embeddings.json` differ
- `retrieve_pg` returns `list[chunk_index]`; the refactored `run_eval` runs against it
- DB-backed Hit@5 / MRR match the Step 3 baseline (8/8, 0.729), or differences are
  explained by HNSW approximation
- `DATABASE_URL` is read from `.env`; a missing value raises a clear error
- No FastAPI / frontend work is introduced

## Step 5 Hand-off

Constraints carried into the FastAPI step — recorded so they aren't rediscovered later:

- **`init_db()` is a setup step, not app code.** Never wire it into FastAPI
  startup/lifespan — DDL on every boot races across instances and masks the migration
  question. Keep it invoked explicitly (scripts / one-time setup).
- **All DB access goes through one accessor in `db/connection.py`.** FastAPI needs a
  connection pool (`psycopg_pool`); a single accessor lets Step 5 swap
  single-connection → pool without touching callers.
- **Migrations deferred, not skipped.** `CREATE TABLE IF NOT EXISTS` bootstraps a fresh
  schema but cannot evolve an existing one. Adopt Alembic at the *first* schema change
  (likely Step 5+); the initial migration = `db/schema.sql` verbatim, then
  `alembic stamp` existing DBs. Keep `schema.sql` as plain DDL so it stays
  copy-pasteable.
- **`load_book` full-wipe is single-book only.** It `TRUNCATE`s all tables — Step 5's
  multi-book upload must replace this with per-book scoped operations: `INSERT` for a
  new book, `DELETE WHERE book_id = ?` to re-ingest one. The clean delete needs
  `ON DELETE CASCADE` on the `chunks` / `chunk_embeddings` FKs — itself the first
  schema change, so it lands with the Alembic adoption above. (`TRUNCATE` also takes a
  whole-table lock that blocks concurrent requests; scoped deletes do not.)
- FastAPI does not require an ORM — raw psycopg carries forward fine. If Step 5 adopts
  SQLAlchemy, Alembic comes with it and replaces `schema.sql` (models become source of
  truth; `vector(1536)` needs `pgvector.sqlalchemy.Vector`).

## Next Step

Step 5 wraps the working parse → chunk → embed → store pipeline in a FastAPI shell
(`POST /books/upload`, `GET /books/:id`, `GET /books/:id/chunks`).
