---
shaping: true
---

# Step 7: Grounded Answer API (`POST /books/{id}/ask`) — Shaping

Step 6 wrapped the pgvector retriever in `POST /books/{book_id}/search` —
book-scoped top-k chunks with citation metadata + cosine `score`, gated on
`status='ready'` (404 / 409 / 422). **Retrieval only — no LLM answer (deferred
to here every step since Step 5).**

Step 7 closes the RAG loop: `POST /books/{book_id}/ask` takes a natural-language
question, **reuses the Step 6 retrieval path** (`embed_query` + `search_chunks`),
assembles a grounded prompt from the retrieved chunks, calls Gemini generation,
and returns a **grounded answer with inline citations** — or a **refusal** when
retrieval is too weak to answer.

Carried in from the Step 5 → 6 hand-off + Step 6 inspection (verbatim drivers):

- `/ask` is the reserved Step 7 endpoint (Step 6 took `/search`).
- Reuse the retrieval path — `embed_query` (`services/embeddings.py`) +
  `search_chunks` (`services/retrieval.py`). **No new retrieval/embedding code.**
- `books.status` gates the endpoint — reject anything not `ready` (404 / 409),
  mirroring `search_book`.
- Scope every query by `book_id` (URL path); cross-book ask is Step 8+.
- **The refusal floor is pre-calibrated.** Step 6 inspection measured, on this
  book + `gemini-embedding-001`: strong match ~0.68, no-relevant-content floor
  ~0.50–0.52, **suggested cutoff ~0.55** — "below it, treat as no relevant
  content (return 找不到相關內容 rather than serving boilerplate) … Tune before
  any 'no answer' UX lands (Step 7+)." Step 7 is where it lands.
- No FastAPI imports in `services/`; dependency runs api → services.
- No central config module yet — env is read at call sites (`os.environ`),
  matching `_max_upload_bytes` / `_upload_dir` in the router.

## Settled decisions (pre-shape forks)

Resolved with the user before shaping (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | Response format | **Single JSON** `{answer, citations[], refused}` after generation completes (no SSE; no frontend consumes streaming yet) |
| D2 | Refusal mechanism | **Pre-LLM score floor**: if best hit's `score < ASK_SCORE_FLOOR` (~0.55), short-circuit — return a refusal *without* calling Gemini (cheap, deterministic, testable) |
| D3 | Citations | **Inline markers + sources**: prompt the model to emit `[1]`,`[2]` markers; response returns the numbered source chunks they point into |
| D4 | Answer language | **Mirror the query** (ZH question → ZH answer even on the EN book) — prompt instructs the model to answer in the user's language |
| D5 | Generation provider/model | **Gemini `gemini-2.5-flash`** (env `GEMINI_GEN_MODEL`). Repo is single-provider Gemini (one key, `make_client()`); a second provider isn't worth it for the MVP |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | `POST /books/{book_id}/ask` returns a grounded, cited answer to a natural-language question over one `ready` book — or a refusal when retrieval is too weak | Core goal |
| **R1** | **Ask endpoint behavior** | Must-have |
| R1.1 | Accept JSON `{ "query": str, "k"?: int }`; validate non-blank `query`, `1 ≤ k ≤ 20` (default `k=5`) — reuse the Step 6 `SearchRequest` validation shape | Must-have |
| R1.2 | Retrieve via the **Step 6 path** — `embed_query(query)` → `search_chunks(conn, book_id, qv, k)`. No new retrieval/embedding code | Must-have |
| R1.3 | **Refusal floor (D2):** if `best score (= 1 - min distance) < ASK_SCORE_FLOOR` (default 0.55, env), return a refusal answer with **no Gemini call** and empty `citations`; `refused=true` | Must-have |
| R1.4 | **Grounded generation:** assemble a prompt numbering the retrieved chunks `[1..k]` with page/section labels; instruct the model to (a) answer **only** from the provided context, (b) cite supporting chunks inline as `[n]`, (c) say it can't answer if the context is insufficient, (d) **answer in the query's language (D4)** | Must-have |
| R1.5 | Response = `{ book_id, query, k, answer, refused, citations[] }` where each citation is the numbered source chunk (`marker`, `chunk_index`, `text`, `page_start/end`, `section_title/path`, `score`) — i.e. `ChunkBase` + `marker` + `score` | Must-have |
| R1.6 | Generation is single-shot, `temperature=0` (reproducible-ish), bounded `max_output_tokens` (env `ASK_MAX_OUTPUT_TOKENS`, default e.g. 1024) | Must-have |
| **R2** | **Status gating** (mirror `search_book`) | Must-have |
| R2.1 | Unknown `book_id` → `404`; `status != 'ready'` → `409` (detail names the status); blank `query` / `k ∉ [1,20]` → `422`. Gate **before** any embed/LLM call | Must-have |
| **R3** | **Boundaries + reuse** | Must-have |
| R3.1 | Generation logic lives in a new `services/generate.py` (prompt assembly + Gemini call + answer/citation shaping); the handler orchestrates only | Must-have |
| R3.2 | No FastAPI imports in `services/`; `services/generate.py` callable from scripts too; Gemini client via the existing `make_client()` | Must-have |
| R3.3 | Reuse `make_client` / retry conventions from `services/embeddings.py`; do not fork a second client setup | Must-have |
| **R4** | **Config from env** | Must-have |
| R4.1 | `GEMINI_GEN_MODEL` (default `gemini-2.5-flash`), `ASK_SCORE_FLOOR` (default `0.55`), `ASK_MAX_OUTPUT_TOKENS` (default `1024`); add to `.env.example` | Must-have |
| **R5** | **Testable without Gemini** | Must-have |
| R5.1 | `pytest` stubs both `embed_query` and the generation call (extend `conftest._no_gemini`), as Step 6 stubbed embeddings — deterministic 200 / refusal / 404 / 409 / 422 tests, no network | Must-have |
| **R6** | **Scope boundaries** | Must-have |
| R6.1 | No streaming (D1), no multi-book ask (R3.2 carry), no reranking / hybrid (Step 8+) | Must-have |
| R6.2 | No conversation history / multi-turn; each `/ask` is stateless | Must-have |
| R6.3 | No automated **answer-quality** eval harness this step — correctness verified by curl smoke (the `eval/` set stays retrieval-only). Answer-quality eval is a candidate Step 8 | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | `services/embeddings.py:embed_query(text) -> list[float]` — RETRIEVAL_QUERY, L2-normalized. `make_client()` reads `GEMINI_API_KEY`, returns `genai.Client()`. Retry conventions (`tenacity`, `_is_retryable` on 429 / ServerError) established here |
| C0.2 | `services/retrieval.py:search_chunks(conn, book_id, qv, k) -> list[ChunkHit]` — book-scoped `<=>` over HNSW; `ChunkHit = ChunkBase + distance` |
| C0.3 | `api/routers/books.py:search_book` — gate (`SELECT status` → 404/409) → `embed_query` → `search_chunks` → `SearchResponse` with `score = 1 - distance`. The exact shape `/ask` mirrors |
| C0.4 | `api/schemas.py` — `SearchRequest{query, k}` (+ blank validator), `SearchHit(ChunkBase + score)`, `SearchResponse`. `services/types.py:ChunkBase` is the shared leaf model |
| C0.5 | `tests/conftest.py:_no_gemini` (autouse) monkeypatches `embed_chunks` + `books.embed_query` with deterministic fakes — the seam Step 7 extends for the generation call |

## A: Thin — single-shot grounded generation in `services/generate.py`

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **`services/generate.py`** — new module. `generate_answer(query, hits) -> AnswerResult` where `AnswerResult = {answer: str, refused: bool}`. Builds the grounded prompt (numbered `[n]` chunk blocks + page/section labels + system instructions: ground-only, cite-inline, refuse-if-insufficient, mirror-language), calls `client.models.generate_content(model=GEMINI_GEN_MODEL, …, config=GenerateContentConfig(temperature=0, max_output_tokens=…))`, returns the text. Reuses `make_client` + the `embeddings.py` retry decorator pattern | |
| **A2** | **Refusal floor** in the handler (or a tiny `generate.should_refuse(hits, floor)` helper): `not hits or (1 - hits[0].distance) < ASK_SCORE_FLOOR` → skip A1 entirely, synthesize a language-appropriate refusal string, `refused=true`, `citations=[]` | |
| **A3** | **`/ask` handler** `POST /books/{book_id}/ask` in `api/routers/books.py`: gate (reuse `search_book`'s `SELECT status` → 404/409) → `embed_query` → `search_chunks` → A2 floor check → A1 generate → build `AskResponse`. `citations` = the retrieved hits numbered `1..k` (drop `distance`, add `marker` + `score = 1 - distance`) | |
| **A4** | **Schemas** in `api/schemas.py`: `AskRequest` (alias/subclass of `SearchRequest` — identical `{query, k}` validation), `Citation(ChunkBase + marker:int + score:float)`, `AskResponse{book_id, query, k, answer, refused, citations[]}` | |
| **A5** | **Config helpers** (`api/routers/books.py` or `services/generate.py`): `_gen_model()`, `_score_floor()`, `_max_output_tokens()` reading env with defaults, matching the existing `_upload_dir` style. `.env.example` updated | |
| **A6** | **Tests:** extend `conftest._no_gemini` to monkeypatch `services.generate.generate_answer` (or the underlying `generate_content`) with a deterministic fake that echoes a fixed cited answer; `tests/test_ask.py` covers 404 / 409 / 422 / grounded-200 (answer + ≥1 citation) / refusal-floor-200 (`refused=true`, no citations, no Gemini call) | |

**Citations = all retrieved sources, numbered.** The model emits `[n]` markers
into the answer text; `citations[]` returns chunks `1..k` so the client can
resolve any marker. (Filtering to *only* markers the model actually used → Shape
B; flagged below.)

## B: Structured-output — model returns `{answer, used_markers[]}`

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | Same as A1–A3, but the generation call uses Gemini **structured output** (`response_mime_type="application/json"` + `response_schema`) to return `{answer: str, used_markers: list[int]}` | ⚠️ |
| **B2** | `citations[]` is filtered to **only** the chunks the model reports using — faithful per-answer attribution, no unused sources in the payload | |
| **B3** | Refusal can be expressed in-band (`used_markers=[]` + a refusal `answer`), unifying the floor path and the model-decides path | ⚠️ |

B buys faithful citation filtering at the cost of structured-output prompt
complexity, a JSON-parse failure mode to handle, and harder test stubbing (⚠️).
The model self-reporting `used_markers` is also not guaranteed faithful — it can
claim markers it didn't ground on. For an MVP that already short-circuits the
hard refusal case with a deterministic floor (D2), the extra machinery isn't
earning its keep yet.

## Fit Check

| Req | Requirement | A | B |
|-----|-------------|---|---|
| R0 | `/ask` → grounded cited answer or refusal, scoped to a `ready` book | ✅ | ✅ |
| R1.1 | `{query, k?}` validation reusing Step 6 shape | ✅ | ✅ |
| R1.2 | Retrieve via `embed_query` + `search_chunks` (no new retrieval) | ✅ | ✅ |
| R1.3 | Pre-LLM refusal floor, no Gemini call, empty citations | ✅ | ✅ (B3 folds it in) |
| R1.4 | Grounded prompt: ground-only, inline `[n]`, refuse-if-thin, mirror-language | ✅ | ✅ |
| R1.5 | `{book_id, query, k, answer, refused, citations[]}` | ✅ | ✅ (filtered) |
| R1.6 | Single-shot, `temperature=0`, bounded output | ✅ | ✅ |
| R2.1 | 404 / 409 / 422, gate before embed/LLM | ✅ | ✅ |
| R3.x | `services/generate.py`, no FastAPI in services, reuse `make_client` | ✅ | ✅ |
| R4.1 | Env config (`GEMINI_GEN_MODEL`, `ASK_SCORE_FLOOR`, `ASK_MAX_OUTPUT_TOKENS`) | ✅ | ✅ |
| R5.1 | Deterministic, Gemini-stubbed tests | ✅ | ⚠️ (harder stub) |
| R6.x | No streaming / multi-book / rerank / history / answer-eval | ✅ | ✅ |

**Notes:** Both satisfy every R — the difference is citation *fidelity* vs
*simplicity*, not capability. A returns all `k` numbered sources and lets inline
`[n]` point into them; B uses structured output to return only the cited subset
(⚠️ parse failure mode + harder stub, R5.1). The deterministic floor (D2) already
handles the failure case A's simpler citation model is weakest at.

## Selected Shape

**A: Thin single-shot grounded generation.** Decisions baked in:

1. **Endpoint** — `POST /books/{book_id}/ask`, mirroring `search_book`'s gate +
   retrieval, adding generation. New service `services/generate.py`.
2. **Refusal** — deterministic pre-LLM score floor (D2), env `ASK_SCORE_FLOOR`
   default 0.55, with the Step-6 calibration caveat recorded (re-measure if the
   corpus / embedding model / task_type changes).
3. **Citations** — inline `[n]` markers + all `k` numbered sources (D3); faithful
   marker-filtering (Shape B) deferred until there's a consumer that needs it.
4. **Generation** — Gemini `gemini-2.5-flash` (D5), `temperature=0`, env-bounded
   output, reusing `make_client` + the `embeddings.py` retry conventions.

Open forks remaining (resolve in breadboard, not blocking):

- **F1 — refusal string source:** a fixed per-language constant vs a tiny
  language-detect on the query. Lean: detect CJK vs not (the codebase already has
  `_is_cjk`) → ZH refusal for CJK queries, EN otherwise. Cheap, no model call.
- **F2 — `AskRequest` as subclass vs alias of `SearchRequest`:** identical
  fields/validation. Lean: subclass (or shared base) to avoid drift.
- **F3 — prompt home:** inline string in `generate.py` vs a `prompts/` constant.
  Lean: module-level template constant in `generate.py` for V1.

A has no ⚠️ unknowns and no deferred smells beyond the explicit B-fork.

## Out of Scope — deferred (Step 8+ hand-off)

Topics intentionally excluded from Step 7, recorded so they aren't rediscovered.
Each is a future-step candidate, not a gap in this step.

| Topic | Why deferred | Driver / where it resurfaces |
|-------|--------------|------------------------------|
| **Streaming (SSE) answers** (D1) | No frontend consumes streaming yet; single JSON is simpler + testable | When a UI lands that wants token-by-token output |
| **Multi-book / cross-book ask** | Step 7 scopes by `book_id` (URL path); cross-book needs `WHERE book_id IN (…)` + result fusion | Carried since Step 5/6 hand-off (Step 8+) |
| **Reranking / hybrid (BM25)** | Retrieval is pure pgvector cosine; rerank is a separate retrieval-quality step | Step 6 R6.2 carry; pairs with an answer-quality eval to measure gains |
| **Automated answer-quality eval** (R6.3) | `eval/` stays retrieval-only (Recall@k / MRR); answer correctness verified by curl smoke this step | **Strongest Step 8 candidate** — LLM-as-judge / RAGAS-style faithfulness + answer-relevance over `eval/cases.json` |
| **Faithful citation filtering** (Shape B) | A returns all `k` numbered sources; filtering to only-used markers needs structured output (⚠️) | When a consumer needs strict per-claim attribution |
| **Score-floor recalibration** (D2) | 0.55 is calibrated to *this* book + `gemini-embedding-001` + these task_types | Re-measure the OOS floor if corpus / embedding model / `task_type` changes |
| **Conversation history / multi-turn** (R6.2) | Each `/ask` is stateless | When chat UX is in scope |
| **Answer caching** | No cache; every `/ask` re-embeds + re-generates | Cost/latency optimization once usage justifies it |
| **Auth** | No auth anywhere in the MVP | Carried since Step 5 |
| **`processing`-stuck sweep** (R7.3) | Server crash mid-ingest leaves a row in `processing`, blocking `/ask` (409) like it blocks `/search` | Known MVP gap carried since Step 5; cheap fix = startup `UPDATE … SET status='failed' WHERE status='processing'` |

## Next Step

Breadboard Shape A (the `/ask` handler + `services/generate.py` +
`AskRequest`/`Citation`/`AskResponse` schemas + the floor-vs-generate branch),
then slice — a single vertical slice is expected: one new endpoint, one new
service module, three Pydantic models, one prompt template.
