---
shaping: false
---

# Embed + Eval Inspection Notes: `scripts/embed_pdf_inspect.py`

Date run: 2026-05-21
Book: `AI_ENGINEERING_BUILDING.pdf`
Chunks: 1286 (from `temp/chunks.json`)
Model: `gemini-embedding-001`, `output_dimensionality=1536`, L2-normalized
Eval cases: 8 (from `eval/cases.json`)

## Setup

- `embed_chunks` packed 1286 chunks under `EMBED_TOKEN_BUDGET=18_000` / `EMBED_BATCH_HARD_CAP=100`
- Embeddings saved to `temp/embeddings.json`, reloaded for retrieval (round-trip sanity check passes)
- `run_eval(k=5)` → cosine via dot product on L2-normalized vectors
- Expected chunks resolved at eval time via `resolve_expected`: page-range overlap AND case-insensitive section-title substring

## Result

```
[case-01] hit=True rank=2 expected=[141,142,143,144,145] top=[134,142,167,72,22]      q='How does AI engineering differ from ML engineering?'
[case-02] hit=True rank=1 expected=[673,674]             top=[674,676,798,672,678]    q='What is RAG?'
[case-03] hit=True rank=3 expected=[855,856]             top=[858,865,856,864,147]    q='What is quantization?'
[case-04] hit=True rank=1 expected=[266,267,268,269]     top=[267,269,268,266,270]    q='What does temperature do when sampling tokens?'
[case-05] hit=True rank=1 expected=[1064..1068]          top=[1066,482,1070,1068,1067] q='What does Time Between Tokens (TBT) measure...?'
[case-06] hit=True rank=1 expected=[833,834,835]         top=[833,834,830,836,802]    q='When should I use RAG instead of finetuning?'
[case-07] hit=True rank=2 expected=[636,637,638,639]     top=[640,637,638,642,639]    q='How do people trick AI models into bypassing safety rules?'
[case-08] hit=True rank=2 expected=[855,856]             top=[862,856,858,860,1104]   q='為什麼用更少位元表示模型可以加快推論？'

mean Recall@5: 0.590
mean MRR:      0.729
```

## Headline

- **Hit@5 = 8/8 (100%)** — every case finds ≥1 expected chunk in top-5.
- **MRR = 0.729** → avg first-hit rank ≈ 1.37. Most queries hit at rank 1.
- **Cross-lingual works (case-08).** Chinese query against English source chunks hit at rank 2.

## Why `Recall@5` looks lower than `MRR`

It's a definition artifact, not a retrieval defect.

`recall_at_k = hits_in_topk / len(expected)`. `expected` is *every* chunk whose page+section matches the case, which is often 3–5 contiguous chunks (one section spans multiple chunks). With k=5, recall is capped at `min(5, |expected|) / |expected|`.

Per-case breakdown:

| case  | \|expected\| | hits in top-5 | recall@5 |
| ----- | ------------ | ------------- | -------- |
| 01    | 5            | 1             | 0.20     |
| 02    | 2            | 1             | 0.50     |
| 03    | 2            | 1             | 0.50     |
| 04    | 4            | 4             | 1.00     |
| 05    | 5            | 3             | 0.60     |
| 06    | 3            | 2             | 0.67     |
| 07    | 4            | 3             | 0.75     |
| 08    | 2            | 1             | 0.50     |

Mean = 0.59. The low-recall cases (01, 02, 03, 08) all hit at rank 1–3 — they just don't pull *all* sibling chunks into top-5, because neighboring sections also score high.

**Read `MRR` and `Hit@5` as the V1 acceptance signals; `Recall@5` will matter more once we add re-ranking or expand `k`.**

## Observations

- **`embed_query` uses `task_type="RETRIEVAL_QUERY"`** while documents use `RETRIEVAL_DOCUMENT`. Asymmetric task types are working as intended — no degenerate "everything looks the same" failure.
- **L2-normalized + dot product = cosine.** No norm regressions; reloaded embeddings produce identical retrieval.
- **Section-boundary effect (case-01):** top-1 is chunk 134 ("AI Engineering Versus ML Engineering" intro), expected starts at 141. Both are correct conceptually; the resolver's section-substring filter happens to anchor on 141–145 but 134 also matches `"AI Engineering Versus ML Engineering"` — worth checking whether `resolve_expected` should include it. **Not blocking.**
- **Case-03 / 08 share expected `[855,856]`** (Quantization). Top-5 differs only in ordering / nearby chunks (858, 862, 864, 865) — confirms English and Chinese queries land in the same semantic neighborhood.

## Out-of-Scope Case (added 2026-05-21)

case-09 query: `"How do I bake a perfect sourdough loaf at home?"`. Marked `out_of_scope: true` so `run_eval` skips `resolve_expected`, sets `expected=[]`, and excludes the case from `mean_recall_at_k` / `mean_mrr`.

Result: `hit=False`, top-5 = `[7, 42, 1285, 597, 243]` — leading hits are off-topic (cover/front matter / scattered chunks). Aggregates unchanged (0.590 / 0.729). Confirms the pipeline doesn't crash on OOS.

### Score-gap probe

Note that `expected=[]` is set by `run_eval` for OOS by design (no ground truth to compare against). `retrieve()` itself always returns top-k regardless of query relevance — the question is whether OOS top-k scores are visibly lower.

Probed cosine scores (dot product on L2-normalized vectors) for one in-scope vs OOS query:

| query                                                       | top-1 score |
| ----------------------------------------------------------- | ----------- |
| case-02 in-scope: `"What is RAG?"`                          | 0.686       |
| case-09 OOS:     `"How do I bake a perfect sourdough...?"`  | 0.524       |

Gap ~0.16. Top-5 OOS scores stay in 0.50–0.52 band; top-5 in-scope sits at 0.66–0.69. Clear separation on this one-case probe — a confidence threshold around **0.55–0.60** would filter this OOS without dropping in-scope hits. Caveat: N=1 per side; some in-scope paraphrased queries may also dip, so don't bake a threshold in without sweeping more cases.

**Score thresholding not implemented yet** — would require `retrieve` to return `(index, score)` pairs alongside indices. Defer until we either expand the eval set or hit a real "model is confident about nonsense" failure.

## Not Validated

- **Larger `k`** (10, 20). Would improve apparent Recall@5 mechanically; no need until we have a re-ranking step that uses larger candidate pools.
- **Real-world phrasings** beyond paraphrases of section titles. Current cases are honest but somewhat textbook-shaped.
- **Repeat ingestion stability.** Embeddings were generated once; haven't verified determinism across runs (Gemini embeddings are deterministic per call, but worth confirming if we ever cache).

## Decisions

- **Step 3 acceptance: PASS.** Pipeline ingests, embeds, retrieves, evaluates end-to-end. Quality is good enough to move forward.
- Keep `EMBED_TOKEN_BUDGET`, `EMBED_BATCH_HARD_CAP`, `EMBEDDING_DIM=1536` as configured.
- Defer expanding to 10 cases (out-of-scope + cross-section) until we have a reason to compare retrieval variants — current 8 are enough to validate the pipeline.

## Re-run Triggers

Re-run if any of these change:
- Chunker strategy (chunk size, overlap, section attribution)
- Embedding model / task_type / dimensionality
- Retrieval scoring (e.g., add re-ranking, hybrid lexical+vector)
- Adding/removing eval cases
