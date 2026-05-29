---
shaping: false
---

# Step 6 Inspection Notes: Book-scoped search (`POST /books/{id}/search`)

Date run: 2026-05-29
Scope: V1 — `search_chunks` (A1), `embed_query` relocated to
`services/embeddings.py` (A3), `POST /books/{id}/search` + gating (A4),
schemas (A5), eval rewire deleting `retrieve_pg` (A2/A6)
Stack: `pgvector/pgvector:pg17` (docker compose) + `uvicorn api.main:app`
Book fixture: `00000000-0000-0000-0000-00000000a1e0` —
"AI Engineering: Building Applications with Foundation Models", 1286 chunks
(status forced to `ready` for the smoke; V1's `store_pdf_inspect.py` load
doesn't write the lifecycle)

## Curl smoke

```
POST /books/00000000-0000-0000-0000-00000000a1e0/search
{"query": "What is RAG?", "k": 3}
```

`200`, 3 hits, scores strictly descending, all from the RAG chapter, each
carrying page + section citation metadata:

| rank | chunk_index | score    | page_start–end | section_path                          |
|------|-------------|----------|----------------|---------------------------------------|
| 1    | 674         | 0.685631 | 278–279        | Chapter 6. RAG and Agents → RAG       |
| 2    | 676         | 0.681323 | 279–279        | Chapter 6. RAG and Agents → RAG       |
| 3    | 798         | 0.678162 | 329–329        | Chapter 6. RAG and Agents → Summary   |

Response shape: `{book_id, query, k, hits[]}`; each hit is the 7 `ChunkBase`
fields + `score`. `distance` is dropped at the handler boundary (it's a
retrieval-layer detail, not part of the API contract).

Second probe — Traditional Chinese query (full UTF-8 path, JSON body built with
`jq` to escape correctly):

```
POST /books/00000000-0000-0000-0000-00000000a1e0/search
{"query": "什麼是檢索增強生成？它如何減少模型幻覺？", "k": 3}
```

`200`, no mojibake, all hits in the RAG chapter, scores *higher* than the
English probe:

| rank | chunk_index | score    | page_start–end | section_title    |
|------|-------------|----------|----------------|------------------|
| 1    | 674         | 0.737033 | 278–279        | RAG              |
| 2    | 723         | 0.720817 | 297–297        | RAG Beyond Texts |
| 3    | 798         | 0.709356 | 329–329        | Summary          |

## What `score` means

`score = 1.0 - distance`, computed in the handler (`api/routers/books.py`)
from `ChunkHit.distance`.

- pgvector `<=>` returns **cosine distance** ∈ [0, 2].
- Both query and chunk vectors are L2-normalized (`embed_query` /
  `embed_chunks` both call `l2_normalize`), so cosine distance = 1 − cosine
  similarity.
- Therefore `score = 1 − distance = cosine similarity` ∈ [−1, 1]:
  - `1.0` → vectors point the same direction (maximally relevant)
  - `0` → orthogonal (unrelated)
  - negative → opposed

It is a **relative ranking** signal, not a probability or accuracy. The
0.6856 above corresponds to a ~47° angle between query and chunk — a solid
semantic match for retrieval, but should not be read as "68% correct".
`SearchResponse.hits` is ordered by descending score (= ascending distance),
which is what the smoke confirms.

## Score calibration + suggested cutoff

Measured on this fixture (gemini-embedding-001, asymmetric
RETRIEVAL_QUERY / RETRIEVAL_DOCUMENT task types):

| band | observed | what it is |
|------|----------|------------|
| strong match | ~0.68 (RAG hits above) | genuinely relevant chunk |
| **no-relevant-content floor** | **~0.50–0.52** | unrelated query; top hits are boilerplate (Copyright / Acknowledgments / Colophon) |

The floor came from the OOS probe — query *"How do I bake a perfect sourdough
loaf at home?"* against this AI-engineering book. Top-5 scores: 0.5241, 0.5075,
0.5058, 0.5053, 0.5036, all front-matter sections. So a score of ~0.54 sits
only ~0.02 above pure noise → effectively "no good answer", not a weak-but-real
hit.

**Suggested cutoff: ~0.55** (between the 0.52 floor and the 0.68 strong band).
Below it, treat as no relevant content (return "找不到相關內容" rather than
serving boilerplate); at or above, surface the hit. Not yet wired into the
handler — `search_chunks` / `SearchResponse` return all top-k regardless of
score. Tune before any "no answer" UX lands (Step 7+).

**Caveat:** this threshold is calibrated to *this* book + *this* embedding
model + *these* task types. Re-measure the OOS floor if the corpus, model, or
`task_type` changes — the absolute numbers will shift.

## Retrieval parity (run_eval, via `scripts/store_pdf_inspect.py`)

The pg path now runs through the new `search_chunks` shim (book-scoped):

- pgvector: mean Recall@5 **0.590**, mean MRR **0.729**, Hit 8/8 (OOS case
  correctly misses)
- in-memory reference: identical, top-k per case matches 1:1
- Step 3 baseline: 0.590 / 0.729 — exact match

The `retrieve_pg → search_chunks` rewrite (book-scoping + rich rows) did not
regress ranking. A1 + A6 confirmed.

## What looks right

- **Gate before embed.** Non-`ready` book returns `409` before any Gemini
  call — verified by the deterministic pytest suite (`test_search_not_ready_409`
  with a `failed` book; detail names the status).
- **Score derivation + ordering.** Scores descend monotonically in the curl
  output, matching ascending `<=>` distance.
- **Book scoping.** `WHERE c.book_id = %s` keeps results inside one book even
  with a second book's 1286 vectors present in `chunk_embeddings` (DB had 2572
  rows at run time); pytest `test_search_scoped_to_book` confirms the API never
  leaks cross-book.
- **HNSW index in play.** `EXPLAIN ANALYZE` on the search query shows
  `Index Scan using chunk_embedding_idx on chunk_embeddings` with
  `Order By: (embedding <=> …)` — the auto-named HNSW index is used (the plan
  text doesn't contain "hnsw"; confirmed by index name + Index Scan).
- **Boundaries hold.** `grep -rn "fastapi" services/ db/` returns nothing;
  `ChunkBase` lives in the leaf `services/types.py`, imported by both
  `services/retrieval.py` and `api/schemas.py` — dependency runs api → services.
- **Multilingual query through the full HTTP path.** Curled a Traditional
  Chinese query *"什麼是檢索增強生成？它如何減少模型幻覺？"* (incl. full-width
  `？`) → `200`, top-3 all in the RAG chapter, scores 0.7370 / 0.7208 / 0.7093
  — all in the strong band, *higher* than the English "What is RAG?" (0.6856).
  UTF-8 survives JSON body → FastAPI decode → `embed_query` → response with no
  mojibake. Cross-language retrieval works end-to-end at the API layer.

## Not Validated

- **`embed_query` cost / latency under load.** Each search makes one
  RETRIEVAL_QUERY Gemini call on the request path; not load-tested.
- **k near the bound.** `k=20` (max) only exercised against tiny test books in
  pytest; not curled against the 1286-chunk fixture.
- **Score calibration across books/models.** Scores are comparable within one
  query's result set; cross-query / cross-book thresholds not characterized.

## Re-run Triggers

- `services/retrieval.py` — `search_chunks` SQL, scoping, or row shape
- `api/routers/books.py` `search_book` — gating order, score formula, response
  mapping
- `api/schemas.py` — `SearchRequest`/`SearchHit`/`SearchResponse` or `ChunkBase`
- `services/embeddings.py` `embed_query` — task_type or normalization
- HNSW index definition / `vector_cosine_ops` opclass

## Decision

**Step 6 acceptance: PASS.** `POST /books/{id}/search` returns ranked,
book-scoped, citation-rich hits on a `ready` book; gating (404/409/422) and
scoping verified; retrieval parity with the Step 3 baseline holds through
`search_chunks`. `score` is well-defined (cosine similarity, [−1,1]).
