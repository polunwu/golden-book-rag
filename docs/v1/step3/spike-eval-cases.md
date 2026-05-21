---
shaping: true
---

# Spike: Eval Cases Curation (B7)

## Context

Shape B7 says "hand-curate ~5–10 cases against current `chunks.json` and commit
`temp/eval_cases.json`". The shaping doc already settled on schema `(id, query,
expected_chunk_indices)` (see [shaping.md](./shaping.md) R4.1, B5.1). But the
*how* of curation is undefined: which queries to write, how to determine
expected chunks reliably, and how the eval set survives future chunker changes.

`docs/thoughts.md` previously sketched a more durable schema
(`expected_section_path`, `expected_page_start/end`, `expected_keywords`) —
worth revisiting before committing the first 5–10 cases.

## Goal

Define a concrete, repeatable curation process for the seed eval set so:

1. The 5–10 cases give meaningful signal on `gemini-embedding-001 @ 1536`
   retrieval quality (R4.2)
2. The set survives chunker iteration without full re-curation (Step 2 chunking
   strategy is explicitly expected to change per `docs/thoughts.md` §3)
3. Curation effort is bounded — V1 should not become an annotation project

## Questions

| #     | Question                                                                                                                                                                              |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1    | What query types meaningfully cover an MVP RAG eval? (single-fact lookup, definition, conceptual/synthesis, paraphrased, multi-hop, out-of-scope)                                      |
| Q2    | How are `expected_chunk_indices` determined reliably without circular reasoning (using the embedding model under test to identify ground truth)?                                       |
| Q3    | Is `expected_chunk_indices` the right ground-truth field, or should the eval JSON store more durable identifiers (page range, section path, keywords) and resolve to chunks at eval time? |
| Q4    | What's the minimum N for stable Recall@5 / MRR signal vs sniff-test only? At 5–10 cases, how noisy are the metrics?                                                                    |
| Q5    | How should cases handle multi-chunk truth (a good answer needs chunks X *and* Y) vs alternative-chunk truth (chunks X *or* Y both satisfy)?                                            |
| Q6    | Should queries match the source book's language (English for the current AI Engineering PDF), or include Chinese queries to stress cross-lingual retrieval?                            |
| Q7    | Where do eval cases physically live — `temp/` (transient, gitignored, easy to mutate) or a committed path (durable, but Step 3 shape currently puts them under `temp/`)?               |
| Q8    | What's the recommended workflow to author one case end-to-end? (read chunks → write query → identify expected → sanity test → commit)                                                  |

## Investigation Steps

1. **Skim `temp/chunks.json`** to understand current content topology — section
   distribution, page count, types of material (cover, prose, code, tables) —
   so candidate queries cover representative regions
2. **Review prior thinking** in `docs/thoughts.md` §"Evaluation process" — the
   `retrieval_eval_cases` schema there is more durable than current B5.1; figure
   out why we chose the simpler form and whether to revisit
3. **Survey public RAG eval practice**:
   - BEIR / MTEB conventions for relevance judgments
   - RAG-specific frameworks (RAGAS, TruLens) — what fields they require for retrieval eval
   - Public RAG cookbooks — typical seed-set sizes for sniff tests vs benchmarks
4. **Bound noisiness**: with N=5 cases and binary hit@k, a single case flip
   shifts mean Recall@5 by 0.2. Document this so the user reads the report
   accordingly
5. **Sketch one worked example** end-to-end — pick a real chunk from `chunks.json`,
   write the query, record the chunk_index, show the eval JSON entry — so the
   curation process is concrete and reproducible

## Findings

Sources consulted: current `temp/chunks.json` (1,286 chunks, ~534 pages of *AI
Engineering* by Chip Huyen); `docs/thoughts.md` §"Evaluation process"; RAGAS
metrics docs (`docs.ragas.io`); BEIR repo overview; MTEB blog.

### Q1 — Query typology

A useful sniff-test set covers retrieval failure modes, not just easy lookups.
Recommended mix for 8–10 cases:

| Type           | Count | Example pattern                                          |
| -------------- | :---: | -------------------------------------------------------- |
| Definition     |   2   | "What is X?" — directly named concept in a section title |
| Specific fact  |   2   | "Which technique does the book recommend for Y?"         |
| Conceptual     |   2   | "How does X differ from Y?" — synthesis across chunks    |
| Paraphrased    |   2   | Wording diverges from the book's phrasing                |
| Out-of-scope   |   1   | Topic absent from the book — should retrieve weakly      |
| Cross-section  |   1   | Answer spans 2+ section_paths                            |

Skip multi-hop / reasoning queries — too complex to author cleanly for V1, and
retrieval-only metrics can't tell you whether the LLM can reason over the
chunks anyway.

### Q2 — Identifying expected chunks without circular reasoning

**Risk:** if Gemini retrieval picks "expected" chunks, then the eval measures
whether the model agrees with itself — not whether it's correct.

**Process (lexical-first, manual-verified):**

1. Write the query independently, based on your knowledge of the book
2. Find candidates via lexical search over `chunks.json` — combine `jq` keyword
   filter with section_title filter to drop Cover/TOC/index noise:
   ```bash
   jq -r '.[] | select(.text | test("KEYWORD"; "i")) | select(.section_title != "Cover") |
     "[\(.chunk_index)] p\(.page_start) §\(.section_title): \(.text[0:120])"' temp/chunks.json
   ```
3. Read the candidate chunks and keep only those that actually answer the query
4. Record the surviving `chunk_index` values

This breaks the circle: ground truth comes from lexical/topical match, not from
the embedding model under test.

### Q3 — Schema durability (the important one)

Current B5.1 stores `expected_chunk_indices: list[int]`. **Problem:** chunk
indices reset whenever the chunker changes (chunk size, overlap, block
strategy). `docs/thoughts.md` §3 already commits the project to iterating
chunking strategy — so eval cases tied to indices have ~one chunker change of
shelf life before re-curation.

**Decision: upgrade to durable ground truth + resolve to chunk_indices at
eval time.**

Upgraded schema:

```json
{
  "id": "case-01",
  "query": "How does AI engineering differ from ML engineering?",
  "expected_page_start": 63,
  "expected_page_end": 69,
  "expected_section_substring": "AI Engineering Versus ML Engineering",
  "expected_keywords": ["AI engineering", "ML"]
}
```

Resolver:

```python
def resolve_expected(case: EvalCase, chunks: list[Chunk]) -> list[int]:
    return [
        c["chunk_index"] for c in chunks
        if c["page_start"] <= case["expected_page_end"]
        and c["page_end"]   >= case["expected_page_start"]
        and case["expected_section_substring"].lower() in (c["section_title"] or "").lower()
        # keywords are optional refinement — uncomment if needed
        # and all(kw.lower() in c["text"].lower() for kw in case["expected_keywords"])
    ]
```

This makes eval cases survive Step 2/4/etc. iteration with zero re-curation
cost — the resolver re-maps to current chunk_indices on every run.

### Q4 — Noise at N=5–10

Binary hit, mean Recall@5 at N=5:

- Each case flip shifts mean by 1/N = **0.20** (20 percentage points)
- MRR even noisier (continuous, but few samples)
- Statistical significance: useless. Regression detection: useful.

**Practical reading:**

- Use the seed eval as a *regression sniff test* — "we used to pass 8/10, now
  we pass 4/10" is a real signal even with small N
- Quote individual case results, not just aggregates
- Do not market a "Recall@5 = 0.8" number — it has wide error bars at this N
- Plan to grow to **N=50+** when moving past Step 6 / before any
  chunker/embedder bake-off

### Q5 — Multi-truth convention

Public eval frameworks (BEIR, RAGAS `NonLLMContextPrecisionWithReference`)
treat ground truth as a **set of relevant docs**, with relevance as binary
(or graded; we use binary). Standard Recall@k counts the fraction of relevant
docs found in top-k.

**Keep current B5.4 semantics:** `expected_chunk_indices` (after resolution) is
a set; `recall_at_k = |retrieved[:k] ∩ expected| / |expected|`; MRR = `1 / rank`
of first hit. Naturally handles both "alternative truth" (any-of) and
"conjunctive" (all-of) — a query with 3 expected chunks rewards finding all 3.

### Q6 — Language

The source book is English. Authoring queries in English keeps signal high.
Add **1–2 Chinese queries** about the same content to exercise
`gemini-embedding-001`'s documented cross-lingual capability — this gives early
warning if Chinese retrieval is broken before the user adds Chinese books later.

### Q7 — Storage location

Current shape puts eval cases in `temp/eval_cases.json`. But:

- `temp/` is meant for ephemeral build artifacts (chunks.json, embeddings.json
  — regenerable from PDF)
- Eval cases are **hand-authored intellectual content** — must be committed
- Losing them costs hours of careful work; rebuilding chunks.json costs seconds

**Decision: move out of `temp/`.** Recommended path: **`eval/cases.json`** at
the repo root.

Reasons:

- Co-located storage for future eval artifacts (eval results, additional case
  sets per book)
- Top-level visibility signals first-class status
- Future Step 4+ will add `eval/results/...` from pgvector runs without
  restructuring

The shape's `temp/eval_cases.json` reference and the V1-plan reference both
need updating.

### Q8 — Worked example

From the chunks index (verified via `jq`), the section "AI Engineering Versus
ML Engineering" spans pages 63–69 with 23 chunks (138–160 inclusive after
spot-check). Chunk 141 (p63–64) literally numbers the differences. This is a
clean conceptual case:

```json
{
  "id": "case-01",
  "query": "How does AI engineering differ from ML engineering?",
  "expected_page_start": 63,
  "expected_page_end": 69,
  "expected_section_substring": "AI Engineering Versus ML Engineering",
  "expected_keywords": ["AI engineering", "ML"]
}
```

End-to-end authoring workflow per case (~5 minutes each):

1. **Pick a topic** — scan `jq -r '[.[].section_title] | unique | .[]' temp/chunks.json`
2. **Write the query** in natural language, independent of the book's exact wording
3. **Locate ground truth** — `jq` query with section filter + keyword (Q2 process)
4. **Verify** — read 2–3 candidate chunks; confirm at least one truly answers the query
5. **Record durable fields** — `page_start/end`, `section_substring`, `keywords`
6. **Sanity-test** — call `resolve_expected(case, chunks)` and check the
   returned indices look right

## Decision Summary

| Topic                       | Decision                                                                     |
| --------------------------- | ---------------------------------------------------------------------------- |
| Query mix                   | 2 definition + 2 fact + 2 conceptual + 2 paraphrased + 1 OOS + 1 cross-section |
| Ground-truth process        | Lexical search (jq) + section filter + manual verification (no embedding oracle) |
| Schema                      | 🟡 **Upgrade**: durable fields (`page_start/end`, `section_substring`, `keywords`); resolve at eval time |
| Multi-truth                 | Standard set-relevance; Recall@k = |retrieved ∩ expected| / |expected|       |
| Language mix                | 8 English + 1–2 Chinese                                                       |
| Storage                     | 🟡 **Move out of temp/**: `eval/cases.json` at repo root                      |
| Seed size                   | 10 cases (gives 10pp resolution on aggregates)                                |
| Worked example              | case-01 above — ready to commit                                               |

## Acceptance

✅ Spike complete. All Q1–Q8 answered with decisions or explicit reasoning.

Outcome rippling back into shape:

- **B5.1** — schema upgrade: `(id, query, expected_page_start, expected_page_end, expected_section_substring, expected_keywords)`
- **B5.x (new)** — add `resolve_expected(case, chunks) -> list[int]` resolver
- **B5.5** — `run_eval` calls resolver per case before retrieve
- **B7** — concrete curation workflow + worked example case-01
- **Storage path** — `eval/cases.json` (move out of `temp/`)
- **New R** (R4.4 candidate) — "Eval cases survive chunker iteration without re-curation"
