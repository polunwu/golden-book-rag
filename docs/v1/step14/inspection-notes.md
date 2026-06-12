---
shaping: false
---

# Step 14 — Inspection Notes (hands-on)

Dated, hands-on verification of the hybrid-search-eval spike. Not a planning doc.

## 2026-06-12 — V1 diagnose run (the gate)

**Setup.** Book `652cca68-b7ca-4f41-99f8-c3045dcf20df` — *AI Engineering: Building
Applications with Foundation Models* (Chip Huyen), 1286 chunks, `ready`. Eval set
extended to **22 cases** (21 scored + 1 OOS): the original 11 tagged
`kind:"semantic"`, plus **10 new `kind:"lexical"`** cases (case-13…22) authored
against real chunks — LoRA, MMLU, RLHF, FLOPs, perplexity, BLEU/ROUGE, HumanEval,
beam search, a misspelled "quantizaton" (trigram-tolerance probe), and an
exact-phrase quote ("scaling extrapolation"). All 22 resolve to ≥1 chunk
(`resolve_expected` dry-run, 0 bad).

**Command.** `uv run python scripts/hybrid_eval_inspect.py --book <id> --diagnose`

**Result (dense / HNSW baseline, OOS excluded):**

```
mean Recall@5: 0.526   mean MRR: 0.766

MISSES (hit=False) — 1:
  [lexical ] case-13  expected=[873,874,875] top=[883,880,881,882,889]  LoRA / Parameter-Efficient Finetuning

WEAK (hit but rank>1) — 7:
  [semantic] rank=2 case-01   [semantic] rank=3 case-03   [semantic] rank=2 case-07
  [semantic] rank=2 case-08   [semantic] rank=2 case-11
  [lexical ] rank=4 case-14 (MMLU)   [lexical ] rank=2 case-19 (misspelled quantizaton)

=== GATE: 3 lexical-tagged miss/weak case(s) → proceed to V2 ===
```

**Gate outcome: PROCEED to V2.** Three lexical-tagged cases are mis- or
weakly-retrieved by pure dense:

- **case-13 (LoRA) — a true miss.** Dense returned *adjacent* chunks in the same
  "Parameter-Efficient Finetuning" section (880–889) but not the exact GT
  (873–875). A textbook spot where exact "LoRA" token matching could pull the right
  chunk — the strongest V2 signal.
- **case-14 (MMLU) — rank 4.** The benchmark name is an exact proper noun; lexical
  fusion could lift it into the top-k.
- **case-19 (misspelled "quantizaton") — rank 2.** Dense largely tolerated the typo
  (semantic embedding is spelling-robust); pg_trgm should *also* catch it via
  trigrams. Watch whether hybrid helps or is redundant here.

## 2026-06-12 — V2 three-arm comparison

**Setup.** Same book + 22 cases. pg_trgm migration applied (`946cf5ed086f`):
extension + GIN `gin_trgm_ops` on `chunks.text`. Lexical = `word_similarity(query,
text) DESC` (book-scoped), hybrid = RRF (`c=60`) over dense+lexical, each fetched
`CANDIDATE_K=20`, truncated to 5.

**Command.** `uv run python scripts/hybrid_eval_inspect.py --book <id> --compare`

```
arm        Recall@5      MRR
dense         0.526    0.766
lexical       0.251    0.409
hybrid        0.489    0.752     <-- WORSE than dense on both metrics
```

**Headline: equal-weight RRF hybrid REGRESSES vs pure dense here.** Per-case rank
table (first-hit rank; `*` = hybrid moved vs dense):

- **The one clear win — case-13 (LoRA): dense MISS → hybrid rank 2.** Lexical found
  GT chunk 873 at rank 2 (the exact-token "LoRA" match dense blurred). This is
  precisely the case the V1 gate predicted hybrid would recover. It works.
- **But many regressions, all from lexical injecting noise:** case-02 RAG 1→2,
  case-06 3→… , case-08 2→4, case-19 (typo) 2→5, case-21 HumanEval 1→2. On cases
  dense already nailed, RRF gives the weak lexical arm an **equal vote**, and its
  20 candidates dilute dense's good ranking.
- **case-14 (MMLU) still missed by both** — lexical `word_similarity` matched the
  common words ("what is the benchmark") not the rare token "MMLU"; the GT didn't
  enter lexical's top-20 either. word_similarity dilutes on multi-word queries.

**Diagnosis of the regression (not a bug):** lexical is too weak (0.251) to be an
equal RRF partner. RRF's premise — both lists are decent and consensus helps — fails
when one arm is mostly noise. The single genuine recovery (LoRA) is outweighed by
dilution elsewhere.

**EXPLAIN:** the lexical query seq-scans the book's chunks (GIN not used for KNN
`ORDER BY`, as expected) — ~97ms / 1286 rows. Fine at spike scale (breadboard
finding #3 confirmed: cheap, no need to force the index).

**Implication for the V3 verdict (leaning SKIP equal-weight hybrid):** naive RRF is
net-negative on this corpus. Hybrid is *not dead* but needs one of: (a) **weighted
fusion** (down-weight lexical) or **gate lexical to low-dense-confidence queries**
only; (b) **better lexical** (`strict_word_similarity`, a `<%` threshold filter to
drop junk candidates so RRF only fuses real lexical hits, single-token term
extraction instead of whole-query word_similarity). V3 spot-checks whether the *one*
recovered case (LoRA) changes the actual `/ask` answer — if even the win doesn't
survive to the answer, SKIP is firm.

## 2026-06-12 — V3 answer gate + VERDICT

**Command.** `--answers` — on every case where hybrid's top-k differs from dense's
(21 of 21 scored shifted, mostly by 1–2 chunks), run `decide_answer` with dense vs
hybrid context, compare the grounded `/ask` answers.

**Result: the retrieval differences almost never change the answer — and where they
do, hybrid is worse.**

- **case-13 (LoRA) — the V2 "win" evaporates at the answer level.** Hybrid retrieved
  the exact GT chunk (873) that dense missed, but **both answers are correct and
  equivalent** (dense's is marginally *more* complete). Dense's adjacent chunks
  (880–889) already answered LoRA fine — the retrieval miss didn't matter to `/ask`.
- **case-21 (HumanEval) — hybrid REGRESSES into a refusal.** Dense answers correctly;
  **hybrid refuses** ("couldn't find relevant content") — lexical injected chunks
  that displaced the good one / dropped best-score below `ASK_SCORE_FLOOR`. A real,
  user-visible harm.
- **All other shifted cases (RLHF, FLOPs, perplexity, BLEU, quantization, scaling
  extrapolation, beam search, …): answers equivalent.** No upside.

### VERDICT — SKIP equal-weight hybrid (do NOT wire into `search_chunks`)

On this corpus, naive RRF dense+lexical is **net-negative**: aggregate retrieval
regression (V2: 0.526→0.489 Recall@5), **zero answer-level upside**, and **at least
one answer-level regression** (a spurious refusal). The exact-term cases we expected
lexical to rescue (LoRA, MMLU, RLHF) are **high-frequency, well-embedded** terms —
dense already serves them. The spike did its job: it stopped a feature that *felt*
obviously good from shipping a regression. R6.1 holds — no production change.

**Revisit only if** one of these changes the premise:
1. **Corpus shifts to rare/OOV-term-heavy content** — niche proper nouns, novel
   jargon, codes/IDs/SKUs the embedding model never saw. Hybrid's value rises exactly
   where dense's embeddings are blind; this book isn't that.
2. **A smarter, cheap lexical variant** — term extraction + `strict_word_similarity`
   + a `<%` threshold so RRF only fuses *real* lexical hits (would likely kill the
   HumanEval refusal regression). Worth a small follow-up *only* if (1) also holds.
3. **CJK never benefits from trigram lexical** — cross-lingual (中文 query → English
   text) has ~zero trigram overlap; a CJK-heavy corpus would need pgroonga/zhparser
   (the rejected D3 options), not pg_trgm.

**Caveat:** n=21 hand-written cases, one well-known book — read the per-case behavior
above, not the means, as the basis for this call (D5).

**Post-verdict cleanup (2026-06-12):** since the verdict is SKIP, the pg_trgm
migration was **downgraded and removed** (extension + `chunks_text_trgm_idx` dropped;
alembic head back to `6f01c766ea52`) — no unused schema cruft. The eval artifacts
(`dense`/`lexical`/`hybrid` retrievers, `--diagnose`/`--compare`/`--answers`) **stay
in `scripts/hybrid_eval_inspect.py`** as the record + a re-runnable harness. Note:
`--diagnose` (dense-only) runs as-is; **`--compare`/`--answers` need pg_trgm
re-added** first (re-create the `CREATE EXTENSION pg_trgm` + GIN migration) — a
deliberate trade for keeping the schema clean while the feature is shelved.

## Findings to carry into V2

1. **CJK lexical stratum (R4.1 v) is N/A for this corpus.** The book is
   English-only; the existing CJK cases (08/10/11/12) are *cross-lingual* queries
   (中文 question → English text). pg_trgm matches **character trigrams**, so a CJK
   query against English text has **~zero trigram overlap** ⇒ the lexical arm
   contributes nothing to cross-lingual cases, and hybrid can only fall back to
   dense for them. This is a real limitation of trigram lexical search, not a bug —
   note it in the V2 verdict. (A true CJK-corpus would need pgroonga/zhparser, the
   rejected D3 options.)
2. **The "weak" (rank>1) signal matters as much as misses.** Only 1 hard miss, but
   7 cases ranked >1 — RRF's value is largely in *re-ranking* these, not just
   recovering misses. V2's per-case delta table should highlight rank movement, not
   only hit/no-hit.
3. **Baseline numbers for comparison:** dense Recall@5 = **0.526**, MRR = **0.766**.
   V2's lexical and hybrid arms are measured against these.

## Code changes verified

- `services/eval.py` — `Retriever` widened to `(qv, text, k)`; `run_eval` call site
  + `retrieve()` updated; `EvalCase.kind` added. `scripts/embed_pdf_inspect.py`
  still imports and runs (the `partial(retrieve, embeddings)` caller absorbs the new
  positional `query_text`). No request-path code touched.
