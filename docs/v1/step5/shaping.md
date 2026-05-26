---
shaping: true
---

# Step 5: FastAPI shell + upload API — Shaping

Step 4 stood up Postgres + pgvector with the architecture-doc schema (`books` /
`chunks` / `chunk_embeddings`) and proved SQL retrieval matches the Step 3 eval
baseline. Step 5 wraps the working parse → chunk → embed → store pipeline in a
thin FastAPI shell, extends the schema to support per-book ingest + status
visibility, and replaces Step 4's single-book full-wipe loader with per-book
scoped operations.

The Step 4 hand-off pre-loaded several constraints that this shaping doc carries
forward verbatim — connection pool via a single accessor, `init_db()` not wired
into the request lifecycle, Alembic adopted at the first schema change, per-book
scoped store ops in place of `TRUNCATE`.

## Requirements (R)

| ID       | Requirement                                                                                                                                                              | Status     |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| R0       | Thin FastAPI shell exposing `POST /books/upload`, `GET /books`, `GET /books/:id`, `GET /books/:id/chunks`, wrapping the working parse → chunk → embed → store pipeline   | Core goal  |
| **R1**   | **Upload endpoint behavior**                                                                                                                                              | Must-have  |
| R1.1     | Accept multipart PDF + a `title` field; validate (PDF content-type, non-empty title, reasonable size cap)                                                                | Must-have  |
| R1.2     | Persist the uploaded PDF to a server-side location keyed by `book_id`; path recorded on the `books` row                                                                  | Must-have  |
| R1.3     | Run parse → chunk → embed → store for the uploaded book end-to-end; rows land in `books` / `chunks` / `chunk_embeddings`                                                 | Must-have  |
| R1.4     | Endpoint returns `202 Accepted` with `book_id` immediately; ingestion runs in the background. Caller polls `GET /books/:id` for status                                   | Must-have  |
| R1.5     | Optional `book_id` field in the request: present+exists → re-ingest (R6.2); present+unknown → `404`; absent → server mints a new id                                       | Must-have  |
| **R2**   | **Read endpoints**                                                                                                                                                        | Must-have  |
| R2.1     | `GET /books/:id` returns book metadata (id, title, file_path, created_at, status, optional error_message); 404 on unknown id                                             | Must-have  |
| R2.2     | `GET /books/:id/chunks` returns chunks for that book with their metadata (`chunk_index`, `text`, page range, section_path/title/level); 404 on unknown id                | Must-have  |
| R2.3     | `GET /books/:id/chunks` paginated via `?limit=&offset=` (default `limit=50`, max `limit=200`); response includes `total` so the caller can iterate                       | Must-have  |
| R2.4     | `GET /books` lists all books with the same shape as R2.1 (id, title, status, …); no pagination required at this stage                                                    | Must-have  |
| **R3**   | **Pipeline stays reusable outside FastAPI** (carries R8 from Step 4)                                                                                                      | Must-have  |
| R3.1     | `services/{pdf_parser, chunker, embeddings, store}.py` callable unchanged from both FastAPI handlers and existing `scripts/`                                              | Must-have  |
| R3.2     | No FastAPI imports leak into `services/` or `db/`                                                                                                                         | Must-have  |
| **R4**   | **DB access** (carries Step 4 hand-off)                                                                                                                                   | Must-have  |
| R4.1     | All DB access flows through one accessor in `db/connection.py`; FastAPI uses a `psycopg_pool` pool, scripts can keep single connections                                   | Must-have  |
| R4.2     | Schema migrations are NOT run from FastAPI startup/lifespan — explicit setup only (`alembic upgrade head` via Makefile / CLI). `init_db()` is removed                    | Must-have  |
| **R5**   | **Schema evolution via Alembic** (carries Step 4 hand-off)                                                                                                                | Must-have  |
| R5.1     | Adopt Alembic; initial revision = current `db/schema.sql` verbatim; existing DBs `alembic stamp`ed                                                                       | Must-have  |
| R5.2     | Alembic revision (separate from R5.3) adds `ON DELETE CASCADE` to `chunks.book_id` and `chunk_embeddings.chunk_id` FKs (enables clean per-book delete for R6.1)           | Must-have  |
| R5.3     | Alembic revision (separate from R5.2) adds `books.status` (enum: `pending` / `processing` / `ready` / `failed`) and `books.error_message TEXT NULL`                       | Must-have  |
| **R6**   | **Per-book scoped storage ops** (replaces Step 4's full-wipe)                                                                                                             | Must-have  |
| R6.1     | Uploading book B does not touch book A's rows; `load_book`'s `TRUNCATE` is replaced with `INSERT` for new books and `DELETE WHERE book_id = ?` for re-ingest              | Must-have  |
| R6.2     | Re-upload = caller supplies the existing `book_id` (R1.5). Server deletes that book's `chunks` / `chunk_embeddings` (CASCADE) and re-runs ingest; other books untouched   | Must-have  |
| **R7**   | **Background processing**                                                                                                                                                 | Must-have  |
| R7.1     | In-process background: upload handler schedules a FastAPI `BackgroundTasks` job that runs the (synchronous) ingest pipeline via `anyio.to_thread.run_sync` so it neither blocks the event loop nor needs an external broker | Must-have  |
| R7.2     | Background task updates `books.status` through its lifecycle: `pending` (row inserted) → `processing` (parse begins) → `ready` (all rows committed) or `failed` (with `error_message`) | Must-have  |
| R7.3     | A background **task** exception always lands the row in `failed` (with `error_message`). **Server crash** mid-ingest leaving a row stuck in `processing` is a known MVP gap — documented, not solved (no startup sweep) | Must-have  |
| R7.4     | Background task does not block FastAPI's request loop (sync ingest runs in a worker thread via R7.1)                                                                      | Must-have  |
| R8       | Config from env (`DATABASE_URL`, `GEMINI_API_KEY`, upload dir); no frontend, no auth, no `/ask` (Step 6+), no retrieval endpoint                                          | Must-have  |

## A: Synchronous upload — caller waits for full ingest (rejected)

| Part | Mechanism                                                                                                                                                | Flag |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| A1   | `POST /books/upload` runs the full parse → chunk → embed → store pipeline inside the request handler, returns `201 Created` + `book_id` when done       |      |
| A2   | No `books.status` column; ingest completion is implicit in the 2xx response                                                                              |      |
| A3   | No background mechanism                                                                                                                                  |      |

Listed only to make the contrast explicit. A multi-minute synchronous handler ties
up a worker, gives the caller no progress signal, and is brittle under client
timeouts. Fails R1.4 (must return 202 immediately), R5.3 / R7.* (no status, no
background lifecycle), and incidentally R5.1–R5.2 / R6.* since none of the schema
work in B has a driver without status + per-book scoping.

## B: FastAPI shell + background ingest + Alembic-managed per-book schema

| Part   | Mechanism                                                                                                                                                                       | Flag |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| **B1** | **FastAPI app package** at `api/`                                                                                                                                                |      |
| B1.1   | 🟡 `api/main.py`: `FastAPI()` instance, mounts routers, configures pool lifespan (acquire pool on startup, close on shutdown — does **not** apply migrations). Filename matches Tiangolo's "Bigger Applications" tutorial — see [spike-fastapi-layout.md](./spike-fastapi-layout.md) |      |
| B1.2   | 🟡 `api/routers/books.py`: the four endpoints (upload, list, get-one, get-chunks); only thing FastAPI-flavoured in the repo. `routers/` (not `routes/`) per Tiangolo convention |      |
| B1.3   | `api/deps.py`: `get_conn()` dependency yielding a pooled connection from `db.connection.get_pool().connection()`; handlers `Depends(get_conn)` to get a vector-registered conn   |      |
| B1.4   | `api/schemas.py`: Pydantic request/response models (`UploadResponse`, `BookOut`, `ChunkOut`, `BookList`, `ChunkPage`)                                                            |      |
| **B2** | **Connection pool in `db/connection.py`** (extends Step 4's single accessor)                                                                                                     |      |
| B2.1   | Lazy module-level `psycopg_pool.ConnectionPool`; `get_pool() -> ConnectionPool`; `configure=register_vector` so every checked-out conn has the adapter registered                |      |
| B2.2   | Existing `get_connection()` kept for scripts (single conn); FastAPI uses the pool — same accessor module, two entry points                                                       |      |
| **B3** | **Alembic adoption**                                                                                                                                                             |      |
| B3.1   | `alembic init alembic`; `alembic.ini` sets `file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s` so every revision file is sortable by creation time (e.g. `2026_05_26_1430_a1b2_init.py`); `env.py` reads `DATABASE_URL` from env |      |
| B3.2   | Revision `…_init.py`: body = current `db/schema.sql` verbatim (fresh DB → `alembic upgrade head` is equivalent to today's `init_db()`)                                           |      |
| B3.3   | Revision `…_chunks_cascade.py`: `ALTER TABLE chunks DROP CONSTRAINT … ADD CONSTRAINT … ON DELETE CASCADE` (and same for `chunk_embeddings.chunk_id`)                              |      |
| B3.4   | Revision `…_book_status.py`: `CREATE TYPE book_status AS ENUM ('pending','processing','ready','failed')`, `ALTER TABLE books ADD COLUMN status book_status NOT NULL DEFAULT 'pending'`, `ADD COLUMN error_message TEXT` |      |
| B3.5   | `init_db()` removed. Setup = `alembic upgrade head` (added as a `Makefile` target, e.g. `make db-migrate`). `db/connection.py` only exposes connections                          |      |
| **B4** | **Per-book storage ops** in `services/store.py`                                                                                                                                  |      |
| B4.1   | Replace `load_book` with `ingest_book(conn, book_id, chunks, embeddings, title, file_path)` that does: `INSERT INTO books … ON CONFLICT (id) DO UPDATE SET title=…, file_path=…`, then `DELETE FROM chunks WHERE book_id = ?` (CASCADEs embeddings), then `INSERT chunks` + `INSERT chunk_embeddings` — all in one transaction |      |
| B4.2   | No `TRUNCATE`; no implicit "wipe the world". Book A is invisible to Book B's ingest                                                                                              |      |
| B4.3   | Step 4's `scripts/store_pdf_inspect.py` updated to call `ingest_book` with a fixed `book_id` instead of `load_book` → same script keeps working, parity check still runs         |      |
| **B5** | **Background ingest orchestrator** in `services/ingest.py`                                                                                                                       |      |
| B5.1   | `ingest_pdf(book_id, pdf_path, title)`: opens its own pooled connection, sets `status='processing'`, calls `parse_pdf` → `chunk_pdf` → `embed_chunks` → `ingest_book`, sets `status='ready'`; all wrapped in try/except that on any exception sets `status='failed'` + `error_message=str(e)` in a fresh transaction (R7.3) |      |
| B5.2   | Fully synchronous (matches the existing services). FastAPI runs it via `BackgroundTasks` + `anyio.to_thread.run_sync(ingest_pdf, …)` so the event loop stays free (R7.1, R7.4)   |      |
| B5.3   | No `api/` imports — `services/ingest.py` stays callable from scripts too                                                                                                          |      |
| **B6** | **Upload handler flow** (`POST /books/upload`)                                                                                                                                   |      |
| B6.1   | Validate multipart: content-type `application/pdf`, non-empty title, size ≤ `MAX_UPLOAD_MB` (env, default 100 MB)                                                                 |      |
| B6.2   | Resolve `book_id`: if request provides one, `SELECT 1 FROM books WHERE id = ?` — found → re-ingest path; not found → `404 Not Found` ("unknown book_id; omit to create new"). If no id provided, mint a new `uuid4` |      |
| B6.3   | Persist file: `UPLOAD_DIR / f"{book_id}.pdf"` (env-driven dir, default `uploads/`); overwrites on re-ingest                                                                       |      |
| B6.4   | `INSERT books … ON CONFLICT (id) DO UPDATE SET status='pending', error_message=NULL` (so a re-ingest visibly resets state)                                                       |      |
| B6.5   | Schedule `BackgroundTasks.add_task(run_ingest, book_id, pdf_path, title)` where `run_ingest` is `async def run_ingest(...): await anyio.to_thread.run_sync(ingest_pdf, ...)`     |      |
| B6.6   | Return `202 { "book_id": ..., "status": "pending" }`                                                                                                                              |      |
| **B7** | **Read handlers**                                                                                                                                                                |      |
| B7.1   | `GET /books`: `SELECT … FROM books ORDER BY created_at DESC` → `list[BookOut]`                                                                                                   |      |
| B7.2   | `GET /books/:id`: `SELECT … WHERE id = ?` → `BookOut` or 404                                                                                                                      |      |
| B7.3   | `GET /books/:id/chunks?limit=&offset=`: validate `1 ≤ limit ≤ 200` (default 50), `offset ≥ 0`; query chunks + a `SELECT count(*)` for `total`; 404 if book doesn't exist          |      |
| **B8** | **Config + boundaries**                                                                                                                                                          |      |
| B8.1   | `.env.example` gains `UPLOAD_DIR=uploads`, `MAX_UPLOAD_MB=100`; `.gitignore` already covers `.env`                                                                                |      |
| B8.2   | `uploads/` added to `.gitignore`; created on app startup if missing                                                                                                              |      |
| B8.3   | No auth, no CORS config beyond defaults, no `/ask`, no retrieval                                                                                                                  |      |

## Fit Check

| Req  | Requirement                                                                                                  | Status    | A   | B   |
| ---- | ------------------------------------------------------------------------------------------------------------ | --------- | --- | --- |
| R0   | FastAPI shell exposing the four endpoints around the working pipeline                                        | Core goal | ✅  | ✅  |
| R1.1 | Multipart PDF + title validation                                                                             | Must-have | ✅  | ✅  |
| R1.2 | PDF persisted server-side keyed by `book_id`; path recorded                                                  | Must-have | ✅  | ✅  |
| R1.3 | Parse → chunk → embed → store runs end-to-end per upload                                                     | Must-have | ✅  | ✅  |
| R1.4 | 202 Accepted with `book_id` returned immediately; status visible via GET                                     | Must-have | ❌  | ✅  |
| R1.5 | Optional `book_id`: present+exists → re-ingest; present+unknown → 404; absent → new id                       | Must-have | ✅  | ✅  |
| R2.1 | `GET /books/:id` returns metadata incl. status + error_message; 404 unknown                                  | Must-have | ❌  | ✅  |
| R2.2 | `GET /books/:id/chunks` returns chunk rows with metadata; 404 unknown                                        | Must-have | ✅  | ✅  |
| R2.3 | `?limit=&offset=` pagination; default 50 / max 200; `total` in response                                      | Must-have | ✅  | ✅  |
| R2.4 | `GET /books` lists all books                                                                                 | Must-have | ✅  | ✅  |
| R3.1 | Services callable unchanged from FastAPI and from existing `scripts/`                                        | Must-have | ✅  | ✅  |
| R3.2 | No FastAPI imports in `services/` or `db/`                                                                   | Must-have | ✅  | ✅  |
| R4.1 | All DB access via one accessor; FastAPI uses `psycopg_pool`, scripts use single connections                  | Must-have | ✅  | ✅  |
| R4.2 | Schema migrations not run in FastAPI lifespan — explicit `alembic upgrade head`                              | Must-have | ✅  | ✅  |
| R5.1 | Alembic adopted; initial revision = `db/schema.sql` verbatim                                                 | Must-have | ❌  | ✅  |
| R5.2 | Separate revision adds `ON DELETE CASCADE` on `chunks.book_id` + `chunk_embeddings.chunk_id`                 | Must-have | ❌  | ✅  |
| R5.3 | Separate revision adds `books.status` enum + `books.error_message`                                           | Must-have | ❌  | ✅  |
| R6.1 | Per-book scoped ops; no `TRUNCATE`; uploading B leaves A untouched                                           | Must-have | ❌  | ✅  |
| R6.2 | Re-ingest = caller supplies existing `book_id`; CASCADE deletes book's chunks+embeddings; others untouched   | Must-have | ❌  | ✅  |
| R7.1 | In-process `BackgroundTasks` + `anyio.to_thread.run_sync` for the sync ingest pipeline                       | Must-have | ❌  | ✅  |
| R7.2 | Status lifecycle pending → processing → ready / failed                                                       | Must-have | ❌  | ✅  |
| R7.3 | Task exceptions land row in `failed` w/ error_message; server crash mid-ingest = documented MVP gap          | Must-have | ❌  | ✅  |
| R7.4 | Background task does not block the event loop                                                                | Must-have | ❌  | ✅  |
| R8   | Config from env; no frontend / no auth / no `/ask` / no retrieval                                            | Must-have | ✅  | ✅  |

**Notes:**

- A fails R1.4 / R5.3 / R7.* — synchronous upload has no status column, no
  background, no observable lifecycle. A also has no driver for R5.1–R5.2 / R6.*
  since none of the schema/per-book work in B is motivated without status +
  scoped ingest. A is listed only to surface why background was the call.
- B has no flagged unknowns. The known MVP gap is R7.3's server-crash case
  (rows stuck in `processing`) — explicitly out of scope, hand-off below.

## Selected Shape

**B: FastAPI shell + background ingest + Alembic-managed per-book schema.**

## Slice

### Slice 1: One vertical slice — upload, observe, re-ingest

Input:

- Step 4 working state (`books` / `chunks` / `chunk_embeddings`, HNSW index,
  `db/connection.py`, `services/store.py`, eval scripts)
- A PDF on disk (the AI Engineering book used through Steps 1–4)

Output:

- 🟡 Running FastAPI app (`uvicorn api.main:app`) exposing the four endpoints
- Alembic-managed DB with `ON DELETE CASCADE` FKs and `books.status` /
  `books.error_message`
- `POST /books/upload` accepts a multipart PDF, returns `202 + book_id`,
  ingests in the background, and the same book reaches `status='ready'`
  observably via `GET /books/:id`
- Re-uploading with the same `book_id` replaces only that book's chunks +
  embeddings; a second book uploaded in parallel is untouched
- All Step 4 scripts (`scripts/store_pdf_inspect.py`, `scripts/embed_pdf_inspect.py`,
  `scripts/probe_pgvector.py`) still run against the new schema after
  `make db-migrate`

Done when:

- `make db-migrate` runs `alembic upgrade head` against a fresh container and
  yields the same logical schema as Step 4's `init_db()` plus the CASCADE FKs
  and the `status` / `error_message` columns
- 🟡 `uvicorn api.main:app` boots without applying migrations (R4.2)
- `POST /books/upload` (PDF + title) returns `202` with a `book_id`; the row
  appears in `books` with `status='pending'`, transitions to `processing`,
  then to `ready` after the background task completes; `chunks` and
  `chunk_embeddings` are populated for that `book_id`
- Forcing the background task to raise (e.g. corrupt PDF) lands the row in
  `status='failed'` with a non-empty `error_message`
- `POST /books/upload` with an unknown `book_id` returns `404`
- `POST /books/upload` with a known `book_id` re-ingests: previous chunks +
  embeddings for that book disappear (CASCADE) and are replaced; another
  book's rows are unchanged before/after
- `GET /books` lists all books; `GET /books/:id` returns book metadata or
  404; `GET /books/:id/chunks` paginates with `limit/offset/total` and
  returns chunk rows with their metadata
- `services/` and `db/` contain no FastAPI imports (R3.2)
- Step 4 scripts run unchanged in behaviour after the `load_book` →
  `ingest_book` rename (eval Hit@5 / MRR parity vs the Step 3 baseline holds)

## Step 6 Hand-off

Constraints carried into the retrieval-API step — recorded so they aren't
rediscovered later:

- **The pool accessor (`db.connection.get_pool`) is the contract.** Step 6's
  retrieval endpoint must acquire connections through the same dependency
  (`api/deps.py:get_conn`) — never open ad-hoc psycopg connections in a
  handler.
- **`services/retrieval.retrieve_pg` is already pool-agnostic** (takes a
  connection). Wire it into a `POST /books/:id/ask` (or `…/search`) handler
  via the same `Depends(get_conn)` dependency; embed the query with
  `services.eval.embed_query` (Step 3) — no new embedding path.
- **`books.status` gates retrieval.** Step 6 must reject (e.g. `409 Conflict`
  or `404`) retrieval against a book whose status is not `ready` — querying
  a half-ingested book would silently return partial results.
- **R7.3 known gap remains.** A row stuck in `processing` (server crash
  mid-ingest) will block retrieval. Acceptable for MVP; a startup sweep
  (`UPDATE books SET status='failed' WHERE status='processing'` on boot) is
  the obvious cheap fix when it bites.
- **Multi-book retrieval is not yet a thing.** All retrieval queries in
  Step 6 should scope by `book_id` (the URL path); cross-book search would
  need an additional `WHERE book_id IN (...)` filter and is explicitly
  Step 7+.
- **Alembic is now the source of truth for schema.** `db/schema.sql` is kept
  only as the verbatim body of the `…_init` revision — do not edit it
  directly. New columns / indexes land via `alembic revision -m …`.

## Next Step

Step 6 wraps the SQL retriever (`services/retrieval.retrieve_pg`) in a FastAPI
endpoint (`POST /books/:id/ask` or `…/search`) returning top-k chunks for a
query, gated on `books.status = 'ready'`.
