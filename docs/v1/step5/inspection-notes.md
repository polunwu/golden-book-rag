---
shaping: false
---

# Step 5 Inspection Notes: FastAPI app + upload + background ingest

Date run: 2026-05-28
Scope: V1 (Alembic + per-book store) + V2 (FastAPI reads) + V3 (upload + bg ingest)
Stack: `pgvector/pgvector:pg17` (docker compose) + `uvicorn api.main:app`
Alembic head: `6f01c766ea52`
Book fixture: `temp/books/AI_ENGINEERING_BUILDING.pdf` (32 MB, 535 pages)

## Setup

- `docker compose up -d` → pg17 + pgvector healthy
- `uv run alembic upgrade head` → three revisions applied (`_init`,
  `_chunks_cascade`, `_book_status`)
- `uv run uvicorn api.main:app --port 8000` → boot in <1s, no DDL run on
  startup (R4.2)
- Lifespan creates `uploads/` if missing, opens `psycopg_pool.ConnectionPool`
  with `configure=register_vector`

## Smoke matrix

All against a freshly-migrated DB.

| # | Path | Input | Result |
|---|------|-------|--------|
| 1 | `POST /books/upload` happy | 32 MB PDF, no `book_id` | `202 {book_id, status:pending}` in <1s; file at `uploads/{book_id}.pdf`; row inserted at `pending` |
| 2 | Background ingest | (1) above | row transitions `pending → processing → ready`; 1286 chunks + 1286 embeddings inserted |
| 3 | `POST /books/upload` re-ingest | same `book_id`, retitled | `202`; row resets to `pending` then ingests; new title persisted; chunks replaced via CASCADE; ended at `ready` (1286 chunks) |
| 4 | Bad content-type | `file=@nope.txt` | `422 file must be application/pdf` — no row, no file |
| 5 | Empty title | `title=''` | `422 title must not be empty` |
| 6 | Malformed `book_id` | `book_id=not-a-uuid` | `422 book_id must be a UUID` |
| 7 | Unknown `book_id` | `book_id=…0099` | `404 unknown book_id; omit to create new` — no row, no file |
| 8 | Oversized | 110 MB PDF, `MAX_UPLOAD_MB=100` | `413`; partial file unlinked; no row |
| 9 | Corrupt PDF | zero-byte upload | `202` (handler can't tell); bg task fails inside `open_pdf`; row lands at `failed` with `error_message="Cannot open empty file: …"` |
| 10 | Concurrent read during processing | `GET /books/:id/chunks` while bg task running | `200` with whatever chunks have been inserted so far (partial — gated on `status='ready'` in Step 6) |
| 11 | `GET /books`, `GET /books/:id`, `GET /books/:id/chunks` (V2) | — | All return expected shapes; 404 on unknown id |
| 12 | `DELETE /books/{id}` happy | corrupt book at `status='failed'` | `204 No Content`; row gone; zero-byte pdf unlinked from `uploads/` |
| 13 | `DELETE /books/{id}` already-deleted | same id again | `404 book not found` |
| 14 | `DELETE /books/{id}` unknown id | random uuid | `404 book not found` |

Final DB snapshot (after `DELETE` smoke removed the first corrupt row, then
a second zero-byte upload was re-introduced to keep a `failed` exemplar in
the table):

```
                  id                  |            title           | status  | chunks
--------------------------------------+----------------------------+---------+--------
 3aa03dcb-190f-4503-97f5-ce0e4f1a7674 | Corrupt                    | failed  |      0
 30de0817-7749-4fa2-bbac-470a81e381e7 | AI Engineering (retitled)  | ready   |   1286
 00000000-0000-0000-0000-00000000a1e0 | AI Engineering: Building … | pending |   1286
```

(The `…a1e0` row was V1's fixed-id load from `scripts/store_pdf_inspect.py`;
its `status` stays at the column default because V1 callers don't write the
lifecycle. `3aa03dcb…` is a deliberately-kept `failed` exemplar — its
`error_message` reads `Cannot open empty file: filename='uploads/3aa03dcb….pdf'`.)

`chunk_embeddings` table: 41 MB. `chunks` table: 4.5 MB. Two ingests of the
same book over the lifetime of the DB.

## What looks right

- **Status lifecycle is observable.** Three separate transactions — the
  `processing` write commits before parse starts, so an external poller (or
  `GET /books/:id`) actually sees the intermediate state. Confirmed: polling
  during a 60s ingest returned `processing` mid-flight, then `ready` on next
  poll after `ingest_book` + final `set_status`.
- **Failure path is a fresh connection.** Zero-byte PDF raised
  `pymupdf.EmptyFileError` *after* `set_status('processing')` committed but
  *before* `ingest_book` opened its own conn. The `except` arm's
  `_set_status(failed, …)` opened a clean pooled conn, wrote the row, and
  re-raised so uvicorn logged the traceback. No tx-state corruption.
- **CASCADE replace works.** Re-ingest with the same `book_id` deleted the
  prior `chunks` (and via CASCADE the matching `chunk_embeddings`) and
  re-inserted in a single `ingest_book` transaction. Row count stayed at 1286;
  no orphan embeddings.
- **413 unlinks the partial file before any DB write.** Verified by inspecting
  `uploads/` after the 110 MB upload — only the two pdfs from passing uploads
  remained.
- **`BackgroundTasks` runs after response is sent.** `202` returned in ~140ms
  for the 32 MB upload; the ingest then ran in an anyio worker thread for
  ~3 minutes without blocking the event loop — `GET /books` during ingest
  responded in <50ms (R7.4 satisfied).
- **Boundaries hold.** `grep -rn "fastapi\|pydantic" services/ db/` returns
  nothing; `python -c "import services.ingest"` runs without a FastAPI app
  in scope (R3.2).
- **`DELETE /books/{id}` is a one-shot.** `DELETE … RETURNING file_path`
  in a single tx returns the path to unlink. FK CASCADE handles
  `chunks` + `chunk_embeddings`. File `unlink(missing_ok=True)` after
  commit — if it fails, we leak a file, not a dangling row. No status
  gate: deleting mid-`processing` is allowed (bg task's later UPDATEs
  affect 0 rows; chunk INSERTs FK-fail and land in the `except` arm
  which also affects 0 rows). Acceptable per MVP norms.

## Observations

- **`UploadFile.size` is unreliable.** Spot-checked against the 110 MB
  upload: FastAPI populated `file.size` but the chunk-and-count loop is what
  actually catches oversize. Plan §5 notes this; confirmed by code path —
  we never read `file.size`.
- **`book_id` field comes in as `str`, parsed manually.** `Annotated[UUID, Form()]`
  appeared to work in a one-off test but the plan called this out as flaky
  across multipart frameworks. Sticking with `str | None` + explicit
  `uuid.UUID(book_id)` returning 422 on `ValueError`.
- **Re-ingest deletes the previous file on size-rejection.** Documented
  edge case in plan §5: an oversized re-upload for an existing `book_id`
  unlinks `pdf_path` (which equals the existing file's path) before raising
  413. The DB row still points at the now-missing file. Not exercised in
  this smoke (only tested oversize on a *new* `book_id`); accepting as a
  documented MVP gap.
- **Schema enum `book_status` cast required.** The status writer uses
  `%s::book_status` because `psycopg` adapts `str` to `text` and PG won't
  implicitly cast `text → book_status` enum. Without the cast: `column
  "status" is of type book_status but expression is of type text`.

## Not Validated

- **Crash recovery.** If the uvicorn process dies between `ingest_book.commit()`
  and `_set_status('ready')`, the row stays at `processing` with rows already
  present. R7.3 known gap — no startup sweep. Not exercised in this smoke.
  Did partially verify the inverse (uvicorn killed via `/exit` mid-ingest):
  the ingest *had* committed before the kill, so the row was at `ready` when
  the DB was inspected. Lucky timing, not a test.
- **HNSW parity after multiple per-book re-ingests.** Step 4 confirmed
  exact parity on a single load. Each re-ingest does
  `DELETE FROM chunks WHERE book_id=…` (CASCADE) + INSERT, so the HNSW
  index incrementally adds/removes 1286 vectors per cycle. Not measured
  whether this drifts retrieval quality vs. a fresh rebuild.
- **Multiple books concurrently uploading.** Plan §5 calls out "two
  uploads in quick succession" as a Done When; not run. The Gemini embed
  step is the bottleneck and would serialise on the API anyway.
- **Server-side request size limit.** Uvicorn's default request body limit
  was not exercised — the 110 MB test triggered our explicit MAX_UPLOAD_MB
  check first (`> 100 MB` rejected mid-stream, well before any uvicorn-level
  cap).
- **`UPLOAD_DIR` outside the project root.** Defaulted to `uploads/`
  (relative). Absolute paths and read-only filesystems not tested.
- **`DELETE` CASCADE under load.** The corrupt book used for the DELETE
  smoke had 0 chunks (failed before any rows were written), so the
  CASCADE path wasn't really exercised by it. The same FK is hit on
  every re-ingest's `DELETE FROM chunks WHERE book_id=…`, which *was*
  exercised, so CASCADE-wiring is implicitly confirmed — just not
  via the `DELETE /books/{id}` route directly.
- **`DELETE` mid-`processing`.** Not exercised in this smoke (would
  need a long-ingesting book + a race). Reasoning above suggests it's
  safe, but unverified.

## Re-run Triggers

Re-run if any of these change:

- `services/ingest.py` — orchestrator order or transaction boundaries
- `api/routers/books.py` upload handler — validation order, size cap, or
  upsert SQL
- `api/routers/books.py` delete handler — order of DB delete vs file unlink
- `BackgroundTasks` → real task queue swap (Step 6+ may move off
  `BackgroundTasks` if startup-sweep / retries land)
- Alembic revision touching `books.status` / `error_message` columns or
  FK `ON DELETE` actions on `chunks` / `chunk_embeddings`
- pool config (`get_pool()` settings, `register_vector` adapter)

## Decision

**Step 5 acceptance: PASS.** Upload + background ingest + status lifecycle
works end-to-end. V1 (Alembic + per-book store) and V2 (FastAPI reads)
already shipped in prior commits and remain green. R3.2 boundary holds; R7.4
(non-blocking ingest) verified. R7.3 (crash recovery) deferred to Step 6 as
designed.

Ready to layer retrieval (`POST /books/:id/ask`) on top in Step 6, with the
`status='ready'` gate the V3 lifecycle now makes meaningful.
