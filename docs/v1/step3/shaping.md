---
shaping: true
---

# Step 3: Chunks → Embeddings — Shaping

## Requirements (R)

| ID     | Requirement                                                                                                       | Status    |
| ------ | ----------------------------------------------------------------------------------------------------------------- | --------- |
| R0     | 🟡 Generate embedding vectors for every chunk in `temp/chunks.json` using Google `gemini-embedding-001` truncated to 1536-dim (Matryoshka) | Core goal |
| **R1** | **Embedding row carries `chunk_index`, `vector` (list[float]), `embedding_model` (str)**                          | Must-have |
| R1.1   | 🟡 Stored `vector` is L2-normalized (`‖v‖ = 1`) — required because `output_dim=1536 < 3072` native per Gemini docs; lets downstream similarity use dot product and keeps pgvector HNSW efficient | Must-have |
| R2     | Persist embeddings to `temp/embeddings.json`; expose `load_embeddings(path) -> list[Embedding]`                   | Must-have |
| **R3** | **Resilient Gemini API usage**                                                                                    | Must-have |
| R3.1   | Batch multiple chunk texts per API request                                                                        | Must-have |
| R3.2   | Retry with backoff on transient errors (rate limit / 5xx)                                                         | Must-have |
| R3.3   | API key read from env (`GEMINI_API_KEY` via `.env`); never committed                                              | Must-have |
| R3.4   | 🟡 Pre-flight assert: no chunk text exceeds 2,048 tokens (Gemini per-text limit); fail fast if exceeded            | Must-have |
| **R4** | **Eval harness reusable across future ingestion strategies**                                                      | Must-have |
| R4.1   | 🟡 ~5–10 hand-curated cases stored as JSON with **durable ground truth** (`expected_page_start/end`, `expected_section_substring`, `expected_keywords`); resolved to current `chunk_indices` at eval time | Must-have |
| R4.2   | Compute Recall@5 and MRR against in-memory vectors via cosine similarity                                          | Must-have |
| R4.3   | Print per-case results + aggregate metrics for manual inspection                                                  | Must-have |
| R4.4   | 🟡 Eval cases survive chunker iteration without re-curation (no `chunk_index` in stored ground truth)              | Must-have |
| R5     | Step 3 independent from DB / pgvector / FastAPI / frontend                                                        | Must-have |
| R6     | Expose `embed_chunks(chunks) -> list[Embedding]` in `services/embeddings.py` for Step 4                           | Must-have |
| R7     | Debug script in `scripts/` runs end-to-end: load chunks → embed → save → run eval                                 | Must-have |

## A: One API call per chunk (rejected)

| Part | Mechanism                                                                          | Flag |
| ---- | ---------------------------------------------------------------------------------- | :--: |
| A1   | 🟡 Loop over chunks; call `client.models.embed_content(model="gemini-embedding-001", contents=chunk.text, config={"output_dimensionality": 1536})` once per chunk |      |
| A2   | Collect vectors into list in chunk order                                           |      |
| A3   | Persist + eval as in B4–B6                                                         |      |

Fails R3.1: no batching. High latency + rate-limit risk on real books.

## B: Batched embedding pipeline + reusable eval harness

| Part   | Mechanism                                                                                                                                                                   | Flag |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--: |
| **B1** | **Embedding service**                                                                                                                                                       |      |
| B1.1   | `Embedding` TypedDict: `chunk_index: int, vector: list[float], embedding_model: str`                                                                                        |      |
| B1.2   | `embed_chunks(chunks: list[Chunk]) -> list[Embedding]` in `services/embeddings.py`                                                                                          |      |
| B1.3   | 🟡 Pre-flight: count tokens per chunk (tiktoken or `len(text) // 4` heuristic); raise `ValueError` if any chunk > 2,048 tokens before calling Gemini                        |      |
| **B2** | 🟡 **Batched Gemini calls + normalization**                                                                                                                                 |      |
| B2.1   | 🟡 Greedy pack chunks into batches by **aggregate token count**: `EMBED_TOKEN_BUDGET = 18_000` per request (90% of Vertex-documented 20K cap), hard-capped at `EMBED_BATCH_HARD_CAP = 100` texts. Flush when next chunk would exceed either. See [spike-batch-size.md](./spike-batch-size.md). |      |
| B2.2   | Call `client.models.embed_content(model="gemini-embedding-001", contents=batch, config={"output_dimensionality": 1536, "task_type": "RETRIEVAL_DOCUMENT"})`; preserve order; map vectors back to `chunk_index` |      |
| B2.3   | 🟡 L2-normalize each returned 1536-dim vector (`v / np.linalg.norm(v)`) before constructing the `Embedding` row                                                             |      |
| **B3** | **Resilience**                                                                                                                                                              |      |
| B3.1   | 🟡 Wrap each batch call with `tenacity` retry: exponential backoff, cap 5 attempts. **Retry:** `google.genai.errors.ServerError` (5xx) and `ClientError` with code 429. **Do NOT retry:** other `ClientError` (e.g. 400 batch-over-token-cap is deterministic — surfaces a bug in B2.1 packing).        |      |
| B3.2   | 🟡 Load `GEMINI_API_KEY` from `.env` via `python-dotenv`; instantiate `genai.Client()`; raise clear error if missing; ensure `.env` is in `.gitignore`                      |      |
| **B4** | **Persistence**                                                                                                                                                             |      |
| B4.1   | `save_embeddings(embeddings, path)` → `temp/embeddings.json` (list of Embedding dicts)                                                                                      |      |
| B4.2   | `load_embeddings(path) -> list[Embedding]` reads JSON back                                                                                                                  |      |
| **B5** | **Eval harness** in `services/eval.py`                                                                                                                                      |      |
| B5.1   | 🟡 Eval case JSON schema: `[{ "id": str, "query": str, "expected_page_start": int, "expected_page_end": int, "expected_section_substring": str, "expected_keywords": list[str] }]` at `eval/cases.json` (out of `temp/`) |      |
| B5.2   | `embed_query(text) -> list[float]` via `gemini-embedding-001` @ 1536, `task_type="RETRIEVAL_QUERY"`; L2-normalize before return (on-the-fly, no caching)                    |      |
| B5.3   | `retrieve(query_vec, embeddings, k=5) -> list[chunk_index]` via dot product (vectors already normalized, so dot = cosine); ranked descending                                 |      |
| B5.4   | 🟡 `resolve_expected(case, chunks) -> list[int]` — maps durable ground truth to current `chunk_indices` via page-range overlap + section_title substring match              |      |
| B5.5   | `recall_at_k(retrieved, expected, k) -> float` and `mrr(retrieved, expected) -> float`                                                                                      |      |
| B5.6   | 🟡 `run_eval(eval_cases, chunks, embeddings, k=5) -> EvalReport` — calls `resolve_expected` per case before `retrieve`; per-case (query, hit?, first_hit_rank, top_k_indices) + aggregate (mean Recall@5, mean MRR) |      |
| **B6** | **Scripts**                                                                                                                                                                |      |
| B6.1   | 🟡 **Live probe** `scripts/probe_gemini_batch.py`: call `embed_content` with fixed sample at batch sizes 1, 10, 50, 100; record latency + any errors; confirms multi-text input works for `gemini-embedding-001` on the Gemini API before bulk ingestion runs |      |
| B6.2   | 🟡 **Debug script** `scripts/embed_pdf_inspect.py`: load chunks → `embed_chunks` → `save_embeddings` → load `eval/cases.json` → `run_eval(cases, chunks, embeddings)` → print report |      |
| **B7** | 🟡 **Eval cases seed** at `eval/cases.json` (committed; out of `temp/`): hand-curate **10 cases** following [spike-eval-cases.md](./spike-eval-cases.md) typology (2 definition + 2 fact + 2 conceptual + 2 paraphrased + 1 OOS + 1 cross-section), mostly English + 1–2 Chinese for cross-lingual sniff. Ground truth via lexical search + section filter + manual verify (not embedding oracle). Worked example: case-01 in spike doc. |      |

## Fit Check

| Req  | Requirement                                                | Status    | A   | B   |
| ---- | ---------------------------------------------------------- | --------- | --- | --- |
| R0   | Generate embeddings via gemini-embedding-001 @ 1536-dim    | Core goal | ✅  | ✅  |
| R1   | Embedding row: chunk_index, vector, embedding_model        | Must-have | ✅  | ✅  |
| R1.1 | 🟡 Vectors L2-normalized                                   | Must-have | ✅  | ✅  |
| R2   | Persist to temp/embeddings.json + load_embeddings()        | Must-have | ✅  | ✅  |
| R3.1 | 🟡 Batch multiple texts per request                        | Must-have | ❌  | ✅  |
| R3.2 | Retry/backoff on transient errors                          | Must-have | ✅  | ✅  |
| R3.3 | API key from env (.env), never committed                   | Must-have | ✅  | ✅  |
| R3.4 | 🟡 Pre-flight assert: no chunk > 2,048 tokens              | Must-have | ✅  | ✅  |
| R4.1 | 🟡 ~5–10 cases as JSON with durable ground truth           | Must-have | ❌  | ✅  |
| R4.2 | Recall@5 + MRR via cosine                                  | Must-have | ✅  | ✅  |
| R4.3 | Print per-case + aggregate metrics                         | Must-have | ✅  | ✅  |
| R4.4 | 🟡 Eval cases survive chunker iteration                    | Must-have | ❌  | ✅  |
| R5   | Independent from DB/pgvector/FastAPI/frontend              | Must-have | ✅  | ✅  |
| R6   | embed_chunks() exposed in services/embeddings.py           | Must-have | ✅  | ✅  |
| R7   | End-to-end debug script                                    | Must-have | ✅  | ✅  |

**Notes:**

- A fails R3.1: per-chunk calls eliminate batching entirely.
- 🟡 B's R3.1 resolved by [spike-batch-size.md](./spike-batch-size.md): token-budgeted packing (`EMBED_TOKEN_BUDGET=18_000`, `EMBED_BATCH_HARD_CAP=100`) with a live probe before first full ingestion run.
- 🟡 B's R4.1 and R4.4 resolved by [spike-eval-cases.md](./spike-eval-cases.md): durable ground-truth schema (page range + section substring + keywords) + `resolve_expected` at eval time. Storage moved from `temp/eval_cases.json` to `eval/cases.json`.

## Selected Shape

Use **B: Batched embedding pipeline + reusable eval harness**.

## Slice

### Slice 1: Embed chunks + run eval against ground truth

Input:

- `temp/chunks.json` (from Step 2)
- 🟡 `eval/cases.json` (committed; hand-curated; 10 cases with durable ground truth)
- `GEMINI_API_KEY` in `.env`

Output:

- `temp/embeddings.json` (list of Embedding dicts)
- Printed eval report: per-case (query, hit?, first_hit_rank, top_k) + aggregate (mean Recall@5, mean MRR)

Done when:

- Every chunk in `chunks.json` has a corresponding 1536-dim vector (gemini-embedding-001, Matryoshka-truncated) in `embeddings.json` keyed by `chunk_index`
- 🟡 All stored vectors are L2-normalized (`‖v‖ ≈ 1.0` within float tolerance)
- 🟡 Pre-flight rejects any chunk > 2,048 tokens before calling Gemini
- Batched calls (token-budget packing per [spike-batch-size.md](./spike-batch-size.md)); transient errors retry with backoff via `tenacity`
- `GEMINI_API_KEY` loaded from `.env`; missing key raises clear error
- `load_embeddings("temp/embeddings.json")` round-trips
- 🟡 `eval/cases.json` committed (10 cases, durable ground truth — no `chunk_index` in stored cases)
- 🟡 `resolve_expected(case, chunks)` returns at least one `chunk_index` per case (sanity check during dev)
- Eval report prints Recall@5 and MRR; obviously-correct queries can be manually sanity-checked as hits
- 🟡 `services/eval.py` exposes `embed_query`, `retrieve`, `resolve_expected`, `recall_at_k`, `mrr`, `run_eval` (reusable by Step 4)
- No DB / FastAPI / embedding-in-Postgres / frontend work introduced

## Next Step

Step 4 sets up Postgres + pgvector, loads `temp/embeddings.json` into `chunk_embeddings`, and verifies similarity search through SQL using the same eval harness from `services/eval.py`.
