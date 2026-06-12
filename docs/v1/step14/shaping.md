---
shaping: true
---

# Step 14: Hybrid Search Eval — measure dense vs. dense+lexical — Shaping

Steps 1–7 built the ingest + retrieval pipeline; Steps 8–13 shipped the FE MVP
(Library, Ask, Upload, Status, Delete). Retrieval today is **pure dense semantic
search** (`services/retrieval.py:search_chunks` — pgvector `<=>` cosine over HNSW,
1536-d L2-normalized Gemini embeddings). The open question: **would hybrid search
(dense + lexical) retrieve better, and how do we know?**

Step 14 does **not** ship hybrid retrieval. It is a **decision spike**: produce
*offline evidence* for whether hybrid beats the current dense baseline on this
corpus, so the call to build (or skip) production hybrid is made on data, not vibes.
The deliverable is a comparison run + a written verdict, not a wired-in feature.

The leverage: `services/eval.py` already has the rig. `run_eval(cases, chunks,
retriever, k)` takes a **pluggable** `Retriever = Callable[[list[float], int],
list[int]]` and reports `mean_recall_at_k` / `mean_mrr` with durable ground truth
(`resolve_expected` → page-range overlap + section substring; OOS excluded). A
hybrid eval is *a second `Retriever`* run through the same function — same cases,
same metrics, apples-to-apples.

## Settled decisions (pre-shape forks)

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Diagnose before building** | **First read the current dense *misses*, then decide if lexical can even help.** Run the existing harness, list cases where dense whiffs (`hit=False` / high `first_hit_rank`), and read those queries. If the misses are **lexical-flavored** (exact phrases, proper nouns, rare terms, IDs, acronyms) hybrid is worth building; if they are **semantic/reasoning** misses (paraphrase, multi-hop) hybrid won't fix them — better chunking or a reranker would, and Step 14 *stops here with that finding*. Cheap, and often answers the question for free. |
| D2 | **Fair dense baseline = what ships** | **The dense side of the comparison routes through `search_chunks` (HNSW), not `eval.py:retrieve()`'s brute-force `mat @ q`.** Today's harness scores dense with an in-memory **exact** dot-product, but production serves **approximate** HNSW. Comparing hybrid against the exact retriever would measure a baseline we don't run. Step 14 adds an HNSW-backed `Retriever` (thin wrapper over `search_chunks`) so both arms reflect production. (The exact retriever stays as an optional recall *ceiling* reference, not the baseline.) |
| D3 | **Lexical method: Postgres FTS, in-DB** | **Use Postgres full-text search (`tsvector`/`ts_rank`) for the lexical arm — no new dependency, no external BM25 service.** The chunk text already lives in `chunks.text`; lexical retrieval is one indexed query alongside the vector query. ⚠️ **CJK wrinkle (flagged):** this corpus is CJK (the embedding token estimator has explicit CJK ranges — `services/embeddings.py:_is_cjk`). Postgres' default FTS parser does **not** segment CJK (no whitespace word boundaries), so naive `to_tsvector('simple', text)` will under-tokenize. Options to resolve in breadboard: a CJK-aware FTS config (`pgroonga`/`zhparser`), or `pg_trgm` trigram similarity (parser-free, works on CJK), or restrict the lexical arm to Latin tokens. **This is the one real unknown in Step 14** and the breadboard must pick. |
| D4 | **Fusion: RRF, not weighted scores** | **Fuse the two ranked lists with Reciprocal Rank Fusion (`1/(c+rank)`), not a tuned weighted sum of normalized scores.** RRF has **no weight to tune**, so it can't overfit the small hand-written eval set — critical at low N. Weighted score fusion needs score normalization (cosine vs. `ts_rank` are different scales) *and* a weight tuned on a dev split; deferred unless RRF is clearly leaving signal on the table. |
| D5 | **Decision metric: retrieval primary, answer quality as a gate** | **Recall@k / MRR (from the harness) is the primary comparison, but a retrieval win only counts if it plausibly changes answers.** The product is grounded Q&A — if the right chunk was already in dense top-k, re-ranking it higher may not change the LLM output at all. So a positive retrieval delta is followed by a **spot-check of `/ask` answers** on the shifted cases before declaring hybrid worth shipping. Retrieval gain that doesn't survive to the answer is not a reason to add complexity. |
| D6 | **Eval-set adequacy — confirmed insufficient, must extend** | **The current `eval/cases.json` cannot decide this question; extending it is mandatory, not optional.** An audit (2026-06-12) found **11 scored cases + 1 OOS**, and they are **structurally biased toward dense's home turf**: almost all are conceptual / paraphrase questions ("What is RAG?", "How does AI engineering differ from ML engineering?", "為什麼用更少位元…加快推論？"). Only ~2 carry an exact term ("Time Between Tokens (TBT)", "BM25") — and those terms are high-frequency in this corpus, so dense embeds them well anyway. **There is essentially no case where lexical *should* win** ⇒ running the comparison as-is would falsely conclude "hybrid adds nothing." Two distinct problems: **(a) N too small** — 11 cases can't yield a significant mean-Recall delta (reinforces D5: read per-case, not the mean); **(b) composition biased** — no lexical battleground. Step 14 **must add lexical-stressing cases** (categories below in R4.1), durable ground truth via the same `resolve_expected` contract, stratified ~⅓ lexical / ⅓ semantic / ⅓ mixed across **both** languages, targeting ~25–40 scored cases. The existing 11 stay as the semantic stratum. |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A **decision spike**: diagnose current dense misses (D1); if lexical can help, add an HNSW dense baseline `Retriever` (D2), a Postgres-FTS lexical `Retriever` (D3), and an RRF-fused hybrid `Retriever` (D4); run all through the existing `run_eval` on a lexical-adequate case set (D6) and compare Recall@k / MRR + per-case deltas; gate any "ship it" on an `/ask` answer spot-check (D5). **Output: a written verdict**, not wired-in production retrieval | Core goal |
| **R1** | **Diagnose** | Must-have |
| R1.1 | Run the existing harness against the current dense retriever; produce the **miss list** (cases with `hit=False` or high `first_hit_rank`) and classify each miss **lexical vs. semantic** (D1). If no miss is lexical-flavored, record "hybrid not indicated" and stop | Must-have |
| **R2** | **Comparable retrievers** | Must-have |
| R2.1 | A **dense baseline `Retriever`** backed by `search_chunks` (HNSW), so the baseline = production (D2). Conforms to `Retriever = Callable[[list[float], int], list[int]]` | Must-have |
| R2.2 | A **lexical `Retriever`** over `chunks.text` via Postgres FTS (or the CJK-safe alternative chosen in breadboard — D3), returning ranked `chunk_index`es for the same `k` | Must-have |
| R2.3 | A **hybrid `Retriever`** = RRF over the dense + lexical rankings (D4). Same signature; drops into `run_eval` unchanged | Must-have |
| **R3** | **Comparison** | Must-have |
| R3.1 | Run dense / lexical / hybrid through `run_eval` on the **same cases**, same `k`; report `mean_recall_at_k` and `mean_mrr` per arm **plus the per-case table** (`top_k_indices` / `first_hit_rank`) — the per-case deltas matter more than the mean at small N | Must-have |
| R3.2 | **Answer gate** (D5): for cases where hybrid changes the retrieved set, spot-check `/ask` output (current vs. hybrid context) — does the better retrieval change the grounded answer? | Must-have |
| **R4** | **Eval data** | Must-have |
| R4.1 | The current set (11 scored, semantic-biased — D6) is **confirmed inadequate**; **add lexical-stressing cases** with durable ground truth via the same `resolve_expected` contract, covering the categories below, stratified across both languages, to ~25–40 scored cases. **Missing strata to add:** **(i) rare proper nouns / personal names** quoted verbatim from the book; **(ii) book-specific jargon / low-frequency exact terms** (appear verbatim but seldom); **(iii) numbers / equations / symbols / code identifiers** (e.g. a specific metric value, formula token); **(iv) exact-phrase / verbatim-quote** queries; **(v) CJK exact terms** (a specific 中文 term appearing verbatim — also exercises the D3 CJK tokenizer); **(vi) misspelled / near-form** queries *(only if the breadboard picks `pg_trgm`; drop if FTS)*. The existing 11 conceptual cases are retained as the semantic stratum (D6) | Must-have |
| **R5** | **Reuse the seams** | Must-have |
| R5.1 | Reuse `recall_at_k` / `mrr` / `resolve_expected` / `EvalCase`, `search_chunks`, `embed_query`, and the standalone `get_connection()` script path. **`run_eval` gets a one-line signature widening** — the `Retriever` type + call site pass `case["query"]` so the lexical arm sees the raw text (breadboard finding; the vector alone can't drive `pg_trgm`); scoring/OOS logic untouched. **Add only**: the three `Retriever` wrappers, the pg_trgm lexical SQL + GIN migration (D3), the new eval cases, and a driver `scripts/hybrid_eval_inspect.py` | Must-have |
| **R6** | **Scope boundaries** | Must-have |
| R6.1 | **No production retrieval change** — `search_chunks` and `/ask` are untouched; Step 14 is offline. Wiring hybrid into the request path is a **separate, conditional** step taken only if the verdict is "yes" | Must-have |
| R6.2 | **No cross-encoder reranker, no query expansion/rewriting, no LLM-judge** — those are distinct levers; Step 14 isolates the dense-vs-hybrid retrieval question | Must-have |
| R6.3 | **No new dependency for the lexical arm** if avoidable (in-DB FTS / `pg_trgm`); an external BM25 engine is out of scope | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **`services/eval.py`** — `run_eval(cases, chunks, retriever, k)` loops cases, `embed_query`s each, calls the pluggable `Retriever`, scores `recall_at_k` + `mrr`, excludes `out_of_scope`. **Already the A/B rig** (R5.1). `resolve_expected` maps durable ground truth (page overlap + section substring) → current `chunk_index`es |
| C0.2 | **`eval.py:retrieve()`** — a **brute-force exact** retriever (`mat @ q`, `argsort`). In-memory, not HNSW. Step 14 keeps it as a ceiling reference but **does not** use it as the baseline (D2) |
| C0.3 | **`services/retrieval.py:search_chunks`** — production dense: pgvector `<=>` cosine over HNSW, `query_vec` as L2-normalized `np.ndarray`, scoped to one `book_id`, top-`k`. The dense baseline `Retriever` wraps this (R2.1). **Unchanged** (R6.1) |
| C0.4 | **`chunks.text` / `chunk_embeddings`** — chunk text is stored (lexical arm reads it); embeddings are `vector(1536)`. No FTS index today; Step 14 may add one (R5.1/D3) |
| C0.5 | **Embeddings** — `gemini-embedding-001`, 1536-d, L2-normalized; **CJK-aware** estimator (`_is_cjk`) ⇒ corpus is CJK ⇒ the FTS-tokenization wrinkle (D3 ⚠️) |
| C0.6 | **`scripts/*_inspect.py`** — standalone spikes on `get_connection()` (never the pool). The Step 14 driver follows this pattern (`scripts/hybrid_eval_inspect.py`) — not part of the request path |
| C0.7 | **`/ask` path** (`services/generate.py:decide_answer`) — used **read-only** for the answer-quality spot-check (D5/R3.2); not modified |
| C0.8 | **`eval/cases.json`** — the hand-written `EvalCase`s, loaded by `scripts/embed_pdf_inspect.py` (`run_eval(..., k=5)`). **Current state (2026-06-12 audit): 11 scored + 1 OOS, semantic-biased** — mostly conceptual/paraphrase, ~2 with an exact term (both high-frequency). **Confirmed inadequate** to decide hybrid (D6/R4.1): too few for a mean delta, and no case where lexical should win. Step 14 extends this file |

## A: Offline three-arm comparison via the existing harness (selected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Diagnose** — run `run_eval` on the current dense retriever, dump the miss list, hand-classify lexical vs. semantic (D1/R1.1). Gate: lexical misses present ⇒ proceed; else stop with the finding | |
| **A2** | **Dense baseline `Retriever`** — wraps `search_chunks` (HNSW) to the `Retriever` signature so the baseline = production (D2/R2.1) | |
| **A3** | **Lexical `Retriever`** — Postgres FTS (`to_tsvector`/`ts_rank`) over `chunks.text`, ranked `chunk_index`es; CJK tokenization resolved in breadboard (D3/R2.2) | ⚠️ |
| **A4** | **Hybrid `Retriever`** — RRF fuse of A2 + A3 rankings (`1/(c+rank)`); no tunable weight (D4/R2.3) | |
| **A5** | **Comparison run** — A2/A3/A4 through `run_eval`, same cases + `k`; report means + per-case table (D5 primary metric, R3.1); audit + extend cases with lexical stressors first (D6/R4.1) | |
| **A6** | **Answer gate** — for cases hybrid shifts, spot-check `/ask` answers (D5/R3.2); write the verdict (ship / skip / needs-reranker-instead) | |

A's only flagged unknown is **A3's CJK FTS tokenization** (D3). Everything else
reuses harness + `search_chunks` + the script path; the three `Retriever`s are thin
wrappers over existing calls.

## B: Wire hybrid into `search_chunks` and A/B in production (rejected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | Add a lexical SQL branch + RRF *inside* `search_chunks`, behind a flag | |
| **B2** | Ship both arms; compare on live `/ask` traffic | ⚠️ |

B changes the request path before any offline evidence exists (R6.1), risks
regressing live retrieval, and conflates the measurement with the rollout. There is
no production traffic to A/B against at MVP, and the harness already gives a
controlled comparison for free. Rejected: **measure before you build** (D1), and the
offline harness is the cheaper, safer instrument.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Decision spike: diagnose → comparable retrievers → compare → answer-gate → verdict, no prod change | Core goal | ✅ | ❌ |
| R1.1 | Miss list + lexical/semantic classification; stop if no lexical miss | Must-have | ✅ | ❌ |
| R2.1 | HNSW-backed dense baseline = production | Must-have | ✅ | ✅ |
| R2.2 | Postgres-FTS (CJK-safe) lexical retriever | Must-have | ✅ | ✅ |
| R2.3 | RRF hybrid retriever, harness-pluggable | Must-have | ✅ | ⚠️ |
| R3.1 | Same-cases comparison, means + per-case deltas | Must-have | ✅ | ❌ |
| R3.2 | Answer-quality gate on shifted cases | Must-have | ✅ | ❌ |
| R4.1 | Extend the confirmed-inadequate set with lexical-stressing cases (6 strata) | Must-have | ✅ | ✅ |
| R5.1 | Reuse harness/`search_chunks`/script path (one-line `run_eval` widening); add only the wrappers + pg_trgm SQL/migration + cases + driver | Must-have | ✅ | ❌ |
| R6.1 | No production retrieval change (offline only) | Must-have | ✅ | ❌ |
| R6.2 | No reranker / query-expansion / LLM-judge | Must-have | ✅ | ✅ |
| R6.3 | No new lexical dependency if avoidable | Must-have | ✅ | ✅ |

**Notes:**
- B fails R6.1/R3.1/R5.1: it edits the request path and has no controlled
  same-cases comparison (no MVP traffic to A/B), and conflates measure with ship.
- A and B share the retriever definitions (R2.x); they differ on *where* the
  comparison runs — A in the offline harness (controlled, reversible), B in
  production (risky, premature). The decision spike belongs offline.

## Selected Shape

**A: offline three-arm comparison via the existing harness.** Baked in:

1. **Diagnose first** (A1/D1) — read dense misses, classify; stop if none are
   lexical.
2. **Three comparable `Retriever`s** (A2–A4/D2–D4) — HNSW dense baseline (=prod),
   Postgres-FTS lexical, RRF hybrid — all the `Retriever` signature.
3. **One comparison** (A5/D6/R3.1) — same cases (extended with lexical stressors)
   through `run_eval`; means + per-case deltas.
4. **Answer gate + verdict** (A6/D5) — `/ask` spot-check on shifted cases; write
   ship / skip / reranker-instead.
5. **No production change** (R6.1) — wiring hybrid into `search_chunks` is a
   separate, conditional follow-up.

## Out of Scope — deferred

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Wiring hybrid into `search_chunks` / `/ask`** | Step 14 produces the *verdict*; building prod hybrid is conditional on it (R6.1) | A follow-up step, only if A6 says "ship" |
| **Cross-encoder reranker** | A different lever (re-orders a candidate set); confounds the dense-vs-hybrid question (R6.2) | Separate spike if retrieval is the bottleneck |
| **Query expansion / rewriting** | Orthogonal recall lever; out of this comparison (R6.2) | Separate spike |
| **Weighted score fusion + tuned weights** | RRF is the un-tunable MVP fusion (D4); weighting risks overfitting the small eval set | Revisit only if RRF leaves clear signal unused |
| **LLM-as-judge answer scoring** | The answer gate is a manual spot-check at MVP (D5); automated judging is its own harness | Post-MVP if `/ask` quality needs a metric |
| **Larger / auto-generated eval set** | MVP uses hand-written durable cases (R4.1); scaling the set is separate | When the corpus grows |

## Next Step

Breadboard Shape A — in particular **resolve the A3 CJK-FTS unknown** (`pgroonga`/
`zhparser` config vs. `pg_trgm` vs. Latin-only), then spec the three `Retriever`
wrappers, the RRF helper, the new lexical-stressing `EvalCase`s, and the
`scripts/hybrid_eval_inspect.py` driver. Then slice — likely V1 = diagnose + dense
baseline + lexical + hybrid + comparison run (the whole spike, demo-able: one
command prints the three-arm Recall@k/MRR table + per-case deltas against a real
ingested book), V2 = the answer-quality gate + written verdict. The output is a
**go/no-go on production hybrid**, not a shipped retrieval change.
