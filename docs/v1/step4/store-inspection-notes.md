---
shaping: false
---

# Store + Eval Inspection Notes: `scripts/store_pdf_inspect.py`

Date run: 2026-05-25
Book: `AI_ENGINEERING_BUILDING.pdf`
Chunks: 1286 (from `temp/chunks.json`)
Embeddings: 1286 × 1536 floats, L2-normalized (from `temp/embeddings.json`)
DB: pgvector pg17 via docker compose
Eval cases: 9 (8 in-scope + 1 OOS)

## Setup

- `init_db()` → idempotent schema apply
- `load_book(conn, chunks, embeddings, title, file_path)` — TRUNCATE then INSERT
- Two `run_eval` runs side-by-side, same `k=5`:
  - `partial(retrieve_pg, conn)` — pgvector `<=>` over HNSW
  - `partial(retrieve, embeddings)` — in-memory cosine via dot product (parity reference)
- Both use the same `embed_query` (`task_type="RETRIEVAL_QUERY"`, dim 1536, L2-normalized)

## Result

```
loaded book e217da4b-5f1f-434d-9627-07be1d2f63a7: {'books': 1, 'chunks': 1286, 'chunk_embeddings': 1286}
```

### pgvector retrieval

```
[case-01] hit=True  rank=2 expected=[141..145]   top=[134,142,167,72,22]
[case-02] hit=True  rank=1 expected=[673,674]    top=[674,676,798,672,678]
[case-03] hit=True  rank=3 expected=[855,856]    top=[858,865,856,864,147]
[case-04] hit=True  rank=1 expected=[266..269]   top=[267,269,268,266,270]
[case-05] hit=True  rank=1 expected=[1064..1068] top=[1066,482,1070,1068,1067]
[case-06] hit=True  rank=1 expected=[833,834,835] top=[833,834,830,836,802]
[case-07] hit=True  rank=2 expected=[636..639]   top=[640,637,638,642,639]
[case-08] hit=True  rank=2 expected=[855,856]    top=[862,856,858,860,1104]
[case-09 OOS] hit=False rank=None top=[7,42,1285,597,243]

mean Recall@5: 0.590
mean MRR:      0.729
```

### In-memory retrieval

Identical to pgvector — every case has the same `top` list and the same `rank`.

```
Step 3 baseline: Hit 8/8, Recall@5 0.590, MRR 0.729  ← matches both
```

## Headline

- **Exact parity** between HNSW pgvector and in-memory cosine on all 9 cases.
  Not just same Hit / Recall / MRR aggregates — same top-5 lists in the same
  order. No HNSW approximation drift at 1286 vectors / dim=1536.
- **Loader works as designed.** 1 book + 1286 chunks + 1286 embeddings; counts
  match. TRUNCATE-then-insert is fully idempotent.
- **OOS case behaves identically.** Same off-topic top-5 (`[7, 42, 1285, 597, 243]`)
  as Step 3 — pgvector reproduces the same ordering even for irrelevant queries.

## Why parity is "exact" here

At this corpus size (1286), the HNSW graph default parameters
(`m=16`, `ef_construction=64`, `ef_search=40`) produce a graph dense enough
that top-5 neighbours match exact cosine for every query in the eval set.
The shaping doc's Fit Check anticipated possible drift; in practice we got
zero on this set. Don't assume this holds at 10× or 100× corpus size or with
adversarial queries — re-check parity when corpus grows or when HNSW build
params are tuned for speed.

## Observations

- **Loader runtime ~seconds.** `executemany` with 1286 inserts each for chunks
  and embeddings (1536-dim vector per row) is well within the "no need to
  batch / COPY" zone for V1. Not timed precisely; not the bottleneck.
- **`section_path` (`list[str]`) → `TEXT[]` adapts natively.** No custom dumper
  required. `e["vector"]` (`list[float]`) → `vector(1536)` requires the
  `np.asarray(..., float32)` conversion documented in
  [probe-inspection-notes.md](./probe-inspection-notes.md) and
  [[pgvector-psycopg-dumper]].
- **HNSW index path used in production query too.** Not separately verified
  with EXPLAIN here, but the probe confirmed the planner uses
  `chunk_embedding_idx` for the same `ORDER BY ce.embedding <=> %s LIMIT k`
  shape. If parity ever breaks, EXPLAIN the production query as a first check.

## Not Validated

- **Multi-book scenarios.** Schema supports `book_id`, but `load_book` TRUNCATEs
  all 3 tables on every call — by design for V1 (single-book MVP). Step 5
  multi-book upload MUST replace this with per-book scoped ops; see
  shaping.md Step 5 Hand-off and the comment inline in `services/store.py`.
- **Re-ingestion stability.** Re-running `store_pdf_inspect.py` re-truncates and
  re-inserts; not measured whether HNSW rebuild on every load is acceptable as
  the corpus grows.
- **Concurrent reads during write.** `TRUNCATE` takes an `ACCESS EXCLUSIVE` lock —
  not an issue for V1 (no concurrent readers), but a real problem the moment a
  FastAPI server is in front of this. Step 5 concern.
- **Connection pool behavior.** Single connection per script; `psycopg_pool` is
  Step 5.
- **HNSW `ef_search` tuning.** Defaulted (40). Increasing it may close any
  parity gap that emerges with a larger corpus; not exercised here because
  parity is already exact.

## Re-run Triggers

Re-run if any of these change:

- Any chunker or embedding change that re-runs Step 3 (chunk count / vector
  content changes → baseline shifts → parity needs re-checking)
- HNSW build params in `db/schema.sql` (`m`, `ef_construction`)
- Switch from cosine (`vector_cosine_ops`) to L2 (`vector_l2_ops`) or inner
  product
- Loader strategy change (per-book scoped vs full-refresh)
- Corpus grows by ≥10× (HNSW approximation more likely to bite at scale)

## Decision

**Step 4 acceptance: PASS.** DB-backed retrieval matches in-memory and Step 3
baseline exactly. Schema, loader, and `retrieve_pg` are ready to sit behind a
FastAPI handler in Step 5. No tuning needed before that.
