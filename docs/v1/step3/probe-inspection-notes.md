---
shaping: false
---

# Probe Inspection Notes: `scripts/probe_gemini_batch.py`

Date run: 2026-05-21
Model: `gemini-embedding-001` (Gemini API consumer tier, not Vertex)
SDK: `google-genai`

## Setup

- 100 identical samples of `"sample text " * 50` (~300 est-tokens each)
- Calls `embed_batch_call` (services/embeddings.py) with `task_type="RETRIEVAL_DOCUMENT"` and `output_dimensionality=1536`
- Iterates batch sizes 1 → 10 → 50 → 100
- Measures wall time per call; verifies `dim=1536` returned

## Result

```
batch=  1  ok  vectors=1    dim=1536  0.41s
batch= 10  ok  vectors=10   dim=1536  0.52s
batch= 50  ok  vectors=50   dim=1536  0.86s
batch=100  ok  vectors=100  dim=1536  1.48s
```

All four sizes succeeded. No retries triggered.

## Inferences

- **Batch=100 works on consumer Gemini API.** Confirms the Vertex doc note "each request can only include a single input text" is Vertex-REST-only / stale; does not apply here. See [spike-batch-size.md](./spike-batch-size.md) Q1 + Key Caveat.
- **`EMBED_BATCH_HARD_CAP = 100` is safe** for current usage. No need to drop the cap.
- **Latency scales sub-linearly with batch size.** Per-vector cost:
  - batch=1   → 0.41s/vec
  - batch=10  → 0.052s/vec (~8× cheaper)
  - batch=50  → 0.017s/vec (~24× cheaper)
  - batch=100 → 0.015s/vec (~28× cheaper)
  → Per-request overhead dominates below ~50. Packer should prefer large batches; the token budget is the real ceiling, not text count.
- **Output dim honored.** `output_dimensionality=1536` returned exactly 1536 floats per vector.

## Not Tested

- Aggregate-token cap (18K budget). Sample is ~300 est-tokens × 100 = ~30K est, but Gemini's real tokenizer likely counts less for repeated "sample text "; the call succeeded so the cap was not hit. Real chunks with mixed CJK + English will be denser per char — `_est_tokens` CJK-aware heuristic should keep us under 18K.
- Failure modes (400 over-cap, 429 rate-limit, 5xx). Retry logic in `embed_batch_call` is untested live; only verified by unit-level reasoning. First real ingestion is the next signal.
- Higher batch sizes (250, the Vertex documented ceiling). Not needed — 100 already amortizes overhead.

## Re-run Triggers

Re-run this probe if any of these change:

- Model swap (e.g., `gemini-embedding-001` → `-002`)
- SDK major version bump (`google-genai`)
- Switching to Vertex backend
- Raising `EMBED_BATCH_HARD_CAP` above 100
- Suspected regression: ingestion suddenly slow or hitting 400s

## Decision

Keep `EMBED_BATCH_HARD_CAP = 100` and `EMBED_TOKEN_BUDGET = 18_000` as in plan. Proceed to `scripts/embed_pdf_inspect.py`.
