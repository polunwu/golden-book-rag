---
shaping: true
---

# Step 6: Retrieval API — Shaping

Step 5 stood up the FastAPI shell (`POST /books/upload`, `GET /books`,
`GET /books/:id`, `GET /books/:id/chunks`) over the working parse → chunk →
embed → store pipeline, with Alembic-managed schema, per-book scoped storage,
`books.status` lifecycle, and a pooled `get_conn` dependency.

Step 6 wraps the SQL retriever (`services/retrieval.retrieve_pg`) in a FastAPI
endpoint that returns top-k chunks for a natural-language query, scoped to one
`ready` book. **Retrieval only — no LLM answer generation (Step 7).**

Carried in from the Step 5 hand-off (verbatim drivers):

- The pool accessor (`db.connection.get_pool` → `api/deps.get_conn`) is the
  contract — no ad-hoc connections in handlers.
- `retrieve_pg` is pool-agnostic (takes a connection); embed the query with the
  Step 3 path — no new embedding code.
- `books.status` gates retrieval — reject anything not `ready`.
- Scope every query by `book_id` (URL path); cross-book search is Step 7+.
- The R7.3 known gap remains (a row stuck in `processing` after a server crash
  blocks retrieval) — acceptable for MVP, not solved here.

## Requirements (R)

| ID       | Requirement                                                                                                                                          | Status     |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| R0       | `POST /books/{book_id}/search` wraps the SQL retriever to return top-k chunks for a natural-language query, scoped to one `ready` book                | Core goal  |
| **R1**   | **Search endpoint behavior**                                                                                                                          | Must-have  |
| R1.1     | Accept JSON body `{ "query": str, "k"?: int }`; validate non-empty `query` and `1 ≤ k ≤ K_MAX` (default `k=5`, max `20`)                              | Must-have  |
| R1.2     | Embed the query via the Step 3 retrieval-query path (`task_type="RETRIEVAL_QUERY"`, L2-normalized) — no new embedding code                            | Must-have  |
| R1.3     | Retrieve top-k chunks for **this** book by pgvector cosine distance (`<=>`), using the HNSW index                                                     | Must-have  |
| R1.4     | Response = ordered list of chunks with citation metadata (`chunk_index`, `text`, `page_start/end`, `section_title`, `section_path`) + similarity score | Must-have  |
| **R2**   | **Status gating**                                                                                                                                     | Must-have  |
| R2.1     | Unknown `book_id` → `404 Not Found`                                                                                                                   | Must-have  |
| R2.2     | `book.status != 'ready'` (`pending` / `processing` / `failed`) → `409 Conflict`; never return partial results from a half-ingested book               | Must-have  |
| **R3**   | **Book scoping** (carries Step 5 hand-off)                                                                                                            | Must-have  |
| R3.1     | Retrieval filtered by `book_id`; a search never returns another book's chunks (today's `retrieve_pg` has **no** `book_id` filter — must add one)      | Must-have  |
| R3.2     | Cross-book / multi-book search is out of scope (Step 7+)                                                                                              | Out        |
| **R4**   | **Pipeline stays reusable + boundaries** (carries R3/R4 from Step 5)                                                                                  | Must-have  |
| R4.1     | Retrieval + query-embedding callable from both FastAPI handlers and existing `scripts/`                                                               | Must-have  |
| R4.2     | No FastAPI imports leak into `services/` or `db/`                                                                                                     | Must-have  |
| R4.3     | DB access flows through `get_conn` / the pool accessor; no ad-hoc psycopg connections in the handler                                                  | Must-have  |
| **R5**   | **Eval parity preserved**                                                                                                                             | Must-have  |
| R5.1     | The Step 3/4 eval (`store_pdf_inspect.py` → `run_eval` → `retrieve_pg`) still runs and holds the Hit@5 / MRR baseline after any retrieval refactor    | Must-have  |
| **R6**   | **Scope boundaries**                                                                                                                                  | Must-have  |
| R6.1     | No LLM answer generation, no prompt assembly (Step 7); `search` returns raw chunks only                                                               | Must-have  |
| R6.2     | No auth, no reranking, no hybrid/BM25 (all future)                                                                                                    | Must-have  |

## CURRENT: existing system (baseline)

| Part | Mechanism                                                                                                                          |
| ---- | -------------------------------------------------------------------------------------------------------------------------------- |
| C0.1 | `services/retrieval.retrieve_pg(conn, query_vec, k) -> list[int]` — orders all `chunk_embeddings` by `<=>`, returns `chunk_index`. **No `book_id` filter.** |
| C0.2 | `services/eval.embed_query(text) -> list[float]` — RETRIEVAL_QUERY embed + L2-normalize. Lives in the `eval` (dev/quality) module. |
| C0.3 | `scripts/store_pdf_inspect.py` calls `partial(retrieve_pg, conn)` as the `Retriever` for `run_eval` (returns `chunk_index`).      |
| C0.4 | `api/routers/books.py`: four book endpoints, all via `Depends(get_conn)` + `dict_row` + Pydantic models. No `search` endpoint.   |

## A: Additive — book-scoped search fn replaces `retrieve_pg`, eval migrated to it

| Part   | Mechanism                                                                                                                                                                   | Flag |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| **A1** | **New retrieval fn** `services/retrieval.search_chunks(conn, book_id, query_vec, k) -> list[ChunkHit]` — `WHERE c.book_id = %s ORDER BY ce.embedding <=> %s LIMIT %s`, selecting full chunk cols + `ce.embedding <=> %s AS distance` |      |
| **A2** | 🟡 **Retire `retrieve_pg`.** After A1, `search_chunks` is the only pgvector retriever the repo ships. `services/eval`'s `store_pdf_inspect.py` is migrated onto it (A6), leaving `retrieve_pg` with **no callers → delete it** (no dead code, no two-fn smell, no optional-`book_id` overload) |      |
| **A3** | 🟡 **Relocate `embed_query`** → `services/embeddings.py` (its natural home — it already composes `make_client` + `embed_batch_call` + `l2_normalize` from there). `services/eval.py` re-imports it so `run_eval` is unchanged; the `/search` handler imports `from services.embeddings import embed_query`. Removes the new production→`eval` dependency the handler would otherwise introduce (`embed_query`'s only current caller is `run_eval`). No ⚠️ — pure move + re-export |      |
| **A4** | **Search handler** `POST /books/{book_id}/search` in `api/routers/books.py`: validate body → `SELECT status FROM books WHERE id=%s` (404 / 409 gate) → `embed_query` → `search_chunks` → response |      |
| A5     | Pydantic: `SearchRequest{query, k=5}`, `SearchHit{chunk_index, text, page_start, page_end, section_title, section_path, score}`, `SearchResponse{book_id, query, k, hits}` |      |
| **A6** | 🟡 **Migrate eval parity** in `scripts/store_pdf_inspect.py`: the `Retriever` becomes a `chunk_index` shim over `search_chunks` scoped to the script's fixed `BOOK_ID` — `lambda qv, k: [h.chunk_index for h in search_chunks(conn, BOOK_ID, qv, k)]`. Same `list[int]` contract into `run_eval`, same Hit@5 / MRR baseline (R5.1), and the eval now guards the **shipped** path. Side benefit: fixes the old unfiltered (all-books) eval fragility |      |

## B: Refactor — consolidate retrieval, relocate query-embedding out of `eval`

| Part   | Mechanism                                                                                                                                                                   | Flag |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| **B1** | **Relocate `embed_query`** → `services/retrieval.py` (production home); `services/eval.py` re-imports it for back-compat so `run_eval` is unchanged                          |      |
| **B2** | **Generalize `retrieve_pg`** → `retrieve_pg(conn, query_vec, k, *, book_id=None) -> list[ChunkHit]` returning full rows; eval callback adapts (`hit.chunk_index`)            |  ⚠️  |
| B3     | `store_pdf_inspect.py` updated: `Retriever` shim maps `ChunkHit → chunk_index` so `run_eval` still gets `list[int]` (R5.1)                                                  |  ⚠️  |
| **B4** | **Search handler** — same as A4/A5 but calls the unified `retrieve_pg(..., book_id=book_id)`                                                                                |      |

## Fit Check

| Req  | Requirement                                                                                       | Status    | A   | B   |
| ---- | ------------------------------------------------------------------------------------------------- | --------- | --- | --- |
| R0   | `POST /books/{id}/search` returns top-k chunks for a query, scoped to a `ready` book              | Core goal | ✅  | ✅  |
| R1.1 | JSON `{query, k?}`; validate non-empty query, `1 ≤ k ≤ 20` (default 5)                            | Must-have | ✅  | ✅  |
| R1.2 | Query embedded via Step 3 RETRIEVAL_QUERY path, L2-normalized; no new embedding code              | Must-have | ✅  | ✅  |
| R1.3 | Top-k by `<=>` cosine distance over HNSW                                                          | Must-have | ✅  | ✅  |
| R1.4 | Response = ordered chunks w/ citation metadata + similarity score                                 | Must-have | ✅  | ✅  |
| R2.1 | Unknown `book_id` → 404                                                                            | Must-have | ✅  | ✅  |
| R2.2 | Non-`ready` status → 409; no partial results                                                      | Must-have | ✅  | ✅  |
| R3.1 | Retrieval filtered by `book_id`; no cross-book leakage                                             | Must-have | ✅  | ✅  |
| R4.1 | Retrieval + query-embedding callable from FastAPI and scripts                                     | Must-have | ✅  | ✅  |
| R4.2 | No FastAPI imports in `services/` or `db/`                                                         | Must-have | ✅  | ✅  |
| R4.3 | DB via `get_conn` / pool accessor; no ad-hoc connections                                           | Must-have | ✅  | ✅  |
| R5.1 | Eval still runs + holds Hit@5 / MRR baseline after refactor                                        | Must-have | ✅  | ✅  |
| R6.1 | No LLM answer / prompt assembly; raw chunks only                                                   | Must-have | ✅  | ✅  |
| R6.2 | No auth / rerank / hybrid                                                                          | Must-have | ✅  | ✅  |

**Notes:**

- Both shapes satisfy every R — the difference is code-quality / blast-radius,
  not capability. 🟡 A introduces `search_chunks` as the single retriever,
  migrates the eval onto it, and deletes `retrieve_pg` (no service-signature
  change, no ⚠️). B instead overloads `retrieve_pg` with an optional `book_id`
  and rich rows + moves `embed_query` to a production home — B2/B3 flagged ⚠️
  until the shim is proven against the baseline. 🟡 A reaches the same
  end state as B — one retriever (`search_chunks`) plus `embed_query` in a
  production module (`services/embeddings.py`) — more cleanly, with no ⚠️.
- Open forks below are orthogonal to A vs B.

## Selected Shape

🟡 **A: Additive — new book-scoped search service alongside untouched eval
path.** Decisions:

1. 🟡 **Endpoint** — `POST /books/{book_id}/search`. `/ask` is reserved for the
   Step 7 LLM-answer endpoint.
2. 🟡 **Similarity score** — included per hit as `score = 1 - cosine_distance`
   (`<=>` returns distance; `score` is the convenience for callers / future
   rerank-threshold).
3. 🟡 **Shape A over B** — A reaches B's clean end state more cleanly: add
   `search_chunks` + migrate the eval onto it (A6) + delete `retrieve_pg`, and
   relocate `embed_query` to `services/embeddings.py` (A3). One retriever, both
   retrieval and query-embedding in production modules, no service-signature
   overload, no ⚠️, and eval parity (R5.1) holds via the `chunk_index` shim.

A has no flagged unknowns and no deferred smells.

## Next Step

Breadboard Shape A (the `/search` handler + `search_chunks` retrieval fn +
schemas), then slice — a single vertical slice is expected: one new endpoint,
one retrieval fn, three Pydantic models.
