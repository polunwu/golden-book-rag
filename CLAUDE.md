# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

BookRAG MVP: upload a PDF book, parse → chunk → embed → store, then semantic
search and grounded Q&A with page/section citations. Stack: FastAPI +
PostgreSQL/pgvector (Docker), Gemini for embeddings and generation, `uv` for
deps/runs, `psycopg` (v3) for DB access. Python ≥3.13. No LangChain/LlamaIndex —
the pipeline is hand-rolled and stays that way (see `docs/bookrag_mvp_architecture.md`).
A Next.js frontend lives in `frontend/` (Step 8 onward — see the Frontend section).

## Commands (Makefile)

- `make db-up` / `make db-down` — start/stop the pgvector Postgres container.
- `make db-migrate` — `alembic upgrade head` (run after db-up before tests/serving).
- `make db-reset` — drops the volume (all data lost) + recreates; use on schema changes that aren't migration-covered.
- `make db-shell` — psql into the container.
- `make api-dev` — `uvicorn api.main:app --reload --port 8000`.
- `make test` — `pytest tests/ -v`. **Requires db-up + db-migrate.** Gemini is never called (stubbed, see below).
- Single test: `uv run pytest tests/test_ask.py::test_name -v`.
- New migration: `uv run alembic revision -m "msg"` (autogenerate is not wired — migrations are hand-written raw SQL via `op.execute`).

Run anything Python through `uv run …` (e.g. `uv run python scripts/probe_pgvector.py`); the project is not pip-installed into a global env.

## Architecture

Request → `api/routers/books.py` (the only router) → `services/*`. The router
is thin; all real work lives in `services/`. Two distinct DB-access paths:

- **API path**: `api/deps.py:get_conn` yields a pooled `Connection[DictRow]` from `db.connection:get_pool()`. The pool is opened/closed by `api/main.py`'s lifespan, configured with `row_factory=dict_row` and `configure=register_vector` (every connection has the pgvector adapter).
- **Script/standalone path**: `db.connection:get_connection()` — a single fresh connection. **Scripts MUST NOT call `get_pool()`.**

### Ingest pipeline (background)

`POST /books/upload` streams the PDF to `{UPLOAD_DIR}/{book_id}.pdf` (atomic
`.partial` → rename), upserts a `books` row at status `pending`, and schedules
`services/ingest.py:run_ingest` as a FastAPI `BackgroundTask`. `run_ingest`
offloads the **sync** `ingest_pdf` to a thread (`anyio.to_thread`), which runs:

`open_pdf` (pdf_parser) → `chunk_pdf` (chunker) → `embed_chunks` (embeddings) → `ingest_book` (store)

`services/ingest.py` **owns the `books.status` lifecycle** (`pending → processing → ready → failed`) and is the only place that writes status. On failure it uses a *fresh* connection to record `failed` + `error_message` (the ingest connection may be in an aborted-tx state). **`services/ingest.py` must not import from `api.*`.**

### Retrieval + answer

- `services/retrieval.py:search_chunks` — top-k by pgvector cosine distance (`<=>`, HNSW index). Query vec must be L2-normalized and passed as `np.ndarray` (a plain `list[float]` silently dumps as `float8[]` and breaks `<=>`).
- `services/generate.py:decide_answer` — the single `/ask` decision point with **two refusal gates**: (1) cheap pre-LLM floor (best cosine score < `ASK_SCORE_FLOOR`, no model call), (2) model soft-refusal (`GroundedAnswer.can_answer=False`). Either gate → a language-matched refusal with empty citations, so hard and soft refusals share one contract (`refused=True ⇒ citations=[]`).
- `?retrieve=false` on `/ask` → `generate_plain_answer` (no book context, no citations, skips the ready-gate) — the no-retrieval baseline for UI comparison.
- `services/eval.py` — standalone offline retrieval-eval harness (Recall@k / MRR over hand-written `EvalCase`s). Ground truth is *durable* (page range + section substring), resolved to current `chunk_index`es at eval time via `resolve_expected`; `out_of_scope` cases are excluded from scoring. Not part of the request path — driven from the `scripts/*_inspect.py` spikes.

### Embeddings (`services/embeddings.py`)

Gemini `gemini-embedding-001`, Matryoshka-truncated to **1536** dims, **L2-normalized** (so cosine distance == 1 − dot). Asymmetric task types: chunks use `RETRIEVAL_DOCUMENT`, queries use `RETRIEVAL_QUERY`. Batching is token-budgeted via a CJK-aware estimator (`_est_tokens`); per-text and per-batch caps enforced. All Gemini calls wrapped in `tenacity` retry (`_is_retryable`: ServerError or 429).

### Types / models

`services/types.py:ChunkBase` is the shared Pydantic base; `ChunkHit` (retrieval, adds `distance`), `SearchHit`/`Citation` (API schemas) all derive from it. The pattern in the router is `Model(**hit.model_dump(exclude={"distance"}), score=1.0 - hit.distance)` — keep new fields flowing through `ChunkBase` rather than re-listing columns.

## Data model

`books` (id, title, file_path, created_at, **status** `book_status` enum, **error_message**) → `chunks` (text, page_start/end, section_path `TEXT[]`, section_title/level, chunk_index) → `chunk_embeddings` (chunk_id PK, `vector(1536)`, embedding_model). `chunks → chunk_embeddings` is `ON DELETE CASCADE`; deleting a book cascades to chunks. Ingest is **idempotent per book_id**: `ingest_book` deletes the book's chunks (cascades embeddings) and re-inserts in one transaction. `db/schema.sql` is the reference DDL but **alembic migrations are the source of truth** (the `status`/`error_message` columns exist only in migrations).

## Testing

`tests/conftest.py` monkeypatches the Gemini boundary with deterministic stubs
(`_fake_embed_chunks`/`_fake_embed_query` derive 1536-d normalized vectors from
`chunk_index`; query rng(0) → top hit is chunk_index 0). When stubbing, patch the
name **where it is resolved**: `embed_chunks` on `services.ingest`, `embed_query`
/`generate_plain_answer` on `api.routers.books`, but `generate_answer` on
`services.generate` (because `decide_answer` calls it within its own module).
Tests hit a **real** Postgres; `book_ids` fixture DELETE-CASCADEs created rows on
teardown. Env vars (`UPLOAD_DIR`, `MAX_UPLOAD_MB`, etc.) are re-read per request,
so per-test `monkeypatch.setenv` works.

## Environment

`.env` (loaded via `python-dotenv`) provides `DATABASE_URL` (required by both DB
accessors) and `GEMINI_API_KEY` (required by `make_client`). Tunables read at
call time: `ASK_SCORE_FLOOR` (default 0.6), `GEMINI_GEN_MODEL` (default
`gemini-2.5-flash`), `ASK_MAX_OUTPUT_TOKENS` (1024), `ASK_THINKING_BUDGET`
(default **0** = thinking off — this is extractive RAG), `UPLOAD_DIR` (`uploads`),
`MAX_UPLOAD_MB` (100).

## Frontend (`frontend/`)

Next.js 16 (App Router) + React 19 + TS + Tailwind v4, package manager `yarn`.
Step 8 foundation (`docs/v1/step8/`); feature screens (Library, Ask, Upload, …)
are Steps 9+. **Next 16 has breaking changes vs. training data** (e.g. middleware
→ "proxy") — `frontend/AGENTS.md` says so; check `node_modules/next/dist/docs/`
before writing Next code.

- `make web` runs `next dev` (:3000) — run alongside `make api-dev` (:8000). The browser reaches the backend via `next.config.ts` `rewrites()` `/api/:path*` → `:8000` (strips `/api`): **same-origin, no CORS, backend untouched**. Base URL is `NEXT_PUBLIC_API_BASE_URL` (default `/api`), read once in `src/lib/config.ts`.
- **Data path**: `src/app/page.tsx` (TanStack Query) → `src/api/books.ts` → `src/api/client.ts:request<T>(path, schema)` — the one typed `fetch` wrapper (no axios). Non-2xx or a zod parse-fail → throws `ApiError` (status→friendly message); 2xx → `schema.parse`. This wrapper is also where an auth credential attaches later.
- **Schemas are hand-written zod under `src/api/schemas/`, split by resource** (`book`/`chunk`/`search`/`ask`), mirroring `api/schemas.py` + `services/types.py` — **not generated** (openapi-zod-client was tried and removed: its strict `uuid()`/`datetime()` rejected valid backend data). `ChunkBase` is the shared base, `.extend()`ed by `SearchHit`/`Citation`. Validate **structure only** — `id`/`created_at` are plain `z.string()` (no format policing); zod's default object-strip means additive backend fields don't break parsing. On a backend contract change, edit the matching resource file by hand; the runtime `safeParse` is the drift backstop.
- Only `listBooks()` is wired (the connectivity smoke). App is deliberately **non-indexed** (`metadata.robots` noindex in `app/layout.tsx` + `app/robots.ts` `Disallow: /`).

## Conventions worth knowing

- `scripts/*_inspect.py` and `scripts/probe_*.py` are throwaway exploration/spikes run standalone, not part of the app; they use `get_connection()`, never the pool.
- `docs/v1/stepN/` follows a shaping workflow, in order: `shaping.md` (problem + chosen Shape) → `breadboard.md` (Shape detailed into affordances/wiring) → `slices.md` (vertical increments V1, V2, …) → `V{1,2,3}-plan.md` (per-slice implementation plans). `inspection-notes.md` is a separate dated hands-on verification doc, not a planning step. Docs carry a `shaping: true|false` frontmatter flag. Read the latest step to understand current work-in-flight intent.
- Dynamic SQL: use `psycopg.sql.SQL/Identifier/Literal`, not f-strings (psycopg rejects f-string SQL). Prefer `assert x is not None` over `# type: ignore` for Optional narrowing.
- **Code comments must not reference breadboard/shaping IDs** (`U6`, `N3`, `D5`, `A4`, `R7.1`, `V1`/`V2`, …). Those live in `docs/v1/stepN/`, not the code. Comment only genuinely non-obvious *why*; don't narrate what the code already says.
