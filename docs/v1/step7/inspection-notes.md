---
shaping: false
---

# Step 7 Inspection Notes: Grounded `/ask` (`POST /books/{id}/ask`)

Date run: 2026-06-01
Scope: V1 — `generate_answer` (A1), `should_refuse` / `refusal_text` floor (A2),
`POST /books/{id}/ask` handler + gating (A3), schemas (A4), env readers (A5),
tests (A6)
Stack: `pgvector/pgvector:pg17` (docker compose) + `uvicorn api.main:app`,
real Gemini (`gemini-2.5-flash`, thinking OFF) for generation + embedding
Book fixture: `00000000-0000-0000-0000-00000000a1e0` —
"AI Engineering: Building Applications with Foundation Models", 1286 chunks,
status `ready`
Config: `ASK_SCORE_FLOOR=0.55`, `ASK_MAX_OUTPUT_TOKENS=1024`,
`ASK_THINKING_BUDGET=0`, `k=5`

## Curl smoke

### case-01 — EN grounded (PASS)

```
POST /ask {"query": "How does AI engineering differ from ML engineering?", "k": 5}
```

`200`, `refused=false`, answer carries inline `[1]`–`[5]` markers, 5 citations
with `marker` 1..5 and strictly descending score:

| marker | chunk_index | score  | page  | section_title                      |
|--------|-------------|--------|-------|------------------------------------|
| 1      | 134         | 0.7648 | 60    | The AI Engineering Stack           |
| 2      | 142         | 0.7587 | 64    | **AI Engineering Versus ML Engineering** |
| 3      | 167         | 0.7563 | 72    | Summary                            |
| 4      | 72          | 0.7491 | 36    | From Foundation Models to AI Engineering |
| 5      | 22          | 0.7436 | 15–16 | What This Book Is About            |

case-01's `expected_page_start/end=64` + `expected_section_substring="AI
Engineering Versus ML Engineering"` land at **marker 2**, not the top hit — the
broader "AI Engineering Stack" intro chunk (p.60) outranks the exact section by
0.006. Both are in-set; answer keywords "AI engineering" / "ML" present. The
grounded answer correctly attributes each claim (e.g. "less about model
development and more about adapting and evaluating models [2]" traces to the
p.64 chunk).

### ZH grounded — RAG (PASS)

```
POST /ask {"query": "什麼是檢索增強生成（RAG）？", "k": 5}
```

`200`, `refused=false`, top score 0.7883, **answer fully in Traditional
Chinese** with `[n]` markers preserved. Language mirror works on the grounded
path (prompt instruction "answer in the same language as the question" + the
strong ZH retrieval scores noted in Step 6). No mojibake through the full
UTF-8 → JSON → embed → generate → response round-trip.

### EN OOS — sourdough (PASS, hard refusal)

```
POST /ask {"query": "How do I bake sourdough bread at home?", "k": 5}
```

`200`, `refused=true`, `citations=[]`, English refusal string. Top-5 scores
(direct probe) `0.537, 0.5125, 0.5065, 0.5056, 0.4998`, top section
"Copyright" — front-matter boilerplate, top hit `0.537 < 0.55` floor → **no
Gemini generation call**. Correct hard refusal.

### ZH OOS — pasta (⚠ FALSE NEGATIVE — see Findings)

```
POST /ask {"query": "如何煮一碗好吃的義大利麵？", "k": 5}
```

`200`, `refused=FALSE`. Top-5 scores `0.5589, 0.5531, 0.545, 0.5406, 0.5287`,
top section "Provide Sufficient Context". Top hit `0.5589 ≥ 0.55` floor → the
floor did **not** fire, so generation ran on an off-topic query.

## Findings

### F1 — The 0.55 floor leaks cross-lingual OOS queries

The floor was calibrated in Step 6 against an **English** OOS probe (sourdough,
top ~0.52–0.54). But ZH queries embed with a systematically higher baseline
similarity to this (English) corpus — Step 6 already observed ZH *grounded*
scores running ~0.05 above their EN counterparts (0.737 vs 0.686 for "What is
RAG?"). That same lift applies to ZH **OOS**: the pasta query's top hit
(0.5589) sits *above* the floor while the equivalent EN OOS (0.537) sits below.

So `ASK_SCORE_FLOOR=0.55` is mis-calibrated for ZH: it correctly refuses EN
junk but passes ZH junk. The two OOS bands by language on this fixture:

| query language | OOS top-hit band | vs 0.55 floor |
|----------------|------------------|---------------|
| English        | ~0.53–0.54       | below → refuses ✓ |
| Chinese        | ~0.55–0.56       | above → leaks ✗ |

A follow-up sweep over **all 12 `eval/cases.json` queries** (top-1 score per
query, same fixture) shows the bands *don't* actually overlap once you look past
the two same-language probes — there's a clean ~0.10 gap:

| band                          | top-1 score range | notes |
|-------------------------------|-------------------|-------|
| genuine answerable (10 cases) | **0.6623 – 0.8399** | min = case-03 "What is quantization?"; incl. 4 ZH cases at 0.72–0.79 |
| OOS / off-topic (3 probes)    | **0.5105 – 0.5589** | max = ZH pasta; EN sourdough 0.537; ZH music 0.5105 |

(case-09 in the eval set *is* the OOS sourdough case at 0.5241 — designed to
miss — so it's counted in the OOS band, not the genuine one.)

So a single scalar **does** separate on-topic from off-topic here, just not at
0.55:

- **0.55** — leaks ZH OOS (0.5589) ✗
- **0.56** — clears it by 0.001, zero margin, overfits one probe ✗
- **~0.60** — ✅ ~0.04 above the OOS ceiling (0.5589) and ~0.06 below the
  weakest genuine query (0.6623). Robust both directions.

**Recommended: `ASK_SCORE_FLOOR=0.60`.** Do not exceed ~0.62 or case-03
(quantization, 0.6623) starts getting refused. A language-conditioned floor or
model-side relevance check is still the cleaner long-term answer (and necessary
if the bands ever tighten), but is unwarranted given this gap. **Re-measure both
bands if corpus / embedding model / task_type changes** (carried from Step 6's
caveat) — the absolute numbers, and therefore the safe floor, will shift.

### F2 — Soft refusal isn't language-matched and isn't flagged

When F1 lets an OOS query through the floor, `generate_answer` runs and the
model obeys its "say so plainly" rule — but the ZH pasta query produced an
**English** soft-refusal sentence ("The provided excerpts do not contain enough
information…"), *not* Chinese, despite the language-mirror instruction. And
because the floor didn't fire, the response is `refused=false` with **5
citations attached** to a non-answer. Two gaps:

- the model-side "not enough info" path doesn't honor the language mirror as
  reliably as the grounded path does (likely because there's nothing on-topic
  in-language to anchor on);
- a soft refusal still reports `refused=false` + citations, so a consumer can't
  distinguish "grounded answer" from "model declined". The structured-output
  refusal (Shape B) or a post-generation refusal classifier would close this;
  out of V1 scope.

Both F1 and F2 are floor-calibration / generation-quality issues, not handler
bugs — the wiring is correct.

## What looks right

- **Gate before embed/LLM.** `404` unknown id, `409` non-`ready` (detail names
  status), `422` blank query / `k ∉ [1,20]` all return before any Gemini call —
  deterministic pytest suite (`tests/test_ask.py`) + the refusal-spy test
  (`generate_answer` not called when the floor fires).
- **Hard refusal short-circuits generation.** EN OOS (0.537 < floor) →
  `refused=true`, `citations=[]`, no `generate_content` call. The cheap path
  (no LLM) for clearly-OOS queries works.
- **Citation wiring.** `marker` 1..k in retrieval order, scores descending,
  `distance` dropped at the handler boundary, each citation carries the full
  `ChunkBase` (text + page + section) + `score`. Inline `[n]` in the answer
  align with `marker`.
- **Grounded answers are faithful.** case-01 + ZH-RAG answers cite real chunks
  and the claims trace to the cited text; no obvious outside-knowledge leakage
  in the smoke (not measured — see Not Validated).
- **Boundaries hold.** `grep -rn "fastapi" services/` returns nothing;
  `services/generate.py` reuses `make_client` / `_is_retryable` / `_is_cjk` from
  `services/embeddings.py` and `ChunkHit` from `services/retrieval.py` — deps
  run api → services.
- **Thinking OFF, budget intact.** `gemini-2.5-flash` with
  `thinking_budget=0` returned non-empty `resp.text` on every grounded call;
  no empty-answer RuntimeError. Full 1024-token budget went to the answer.

## Not Validated

- **Answer-quality / faithfulness eval.** `/ask` correctness is curl-eyeballed,
  not measured. `eval/cases.json` is still retrieval-only. LLM-judge / RAGAS
  (faithfulness + answer-relevance) is the strongest Step 8 follow-up.
- **Floor re-calibration confidence.** F1's ~0.60 floor is grounded in a 12-case
  + 3-OOS-probe sweep on *this* fixture, but the genuine band's lower edge rests
  on a single case (case-03, 0.6623); a larger / different corpus could push a
  real query below 0.60. Validate against a broader eval set before trusting the
  floor in production.
- **Latency / cost under load.** Each `/ask` makes one embed + one generate
  Gemini call on the request path; not load-tested. No streaming (single JSON).
- **`k` near the bound / long-context generation.** Only `k=5` curled; `k=20`
  against the 1286-chunk fixture (5× the context) not exercised against the live
  model.
- **`processing`-stuck book.** A crashed-mid-ingest book returns 409 (same as
  `/search`); the startup sweep is still unaddressed (carried from Step 5).

## Re-run Triggers

- `services/generate.py` — prompt, `should_refuse` formula, `refusal_text`
  language pick, retry/thinking config
- `api/routers/books.py` `ask_book` — gating order, floor read, citation mapping
- `api/schemas.py` — `AskRequest` / `Citation` / `AskResponse` or `ChunkBase`
- `ASK_SCORE_FLOOR` / `GEMINI_GEN_MODEL` / embedding model / `task_type` — all
  shift the OOS bands in F1
- `services/embeddings.py` `embed_query` — task_type or normalization

## Decision

**Step 7 acceptance: PASS with a flagged calibration gap.** `POST
/books/{id}/ask` returns grounded, citation-rich answers on a `ready` book;
gating (404/409/422) and hard refusal (no-LLM short-circuit) verified; language
mirror works on the grounded path. **F1 fixed in-step: `ASK_SCORE_FLOOR` raised
0.55 → 0.60** after a 12-case + 3-OOS sweep showed a clean ~0.10 gap (OOS ≤0.559,
genuine ≥0.662); 0.60 catches the ZH-OOS leak with margin on both sides. **F2
remains (out of V1 scope): a query that still clears the floor can produce a
non-language-matched soft refusal reported as `refused=false` + citations** —
wants structured-output refusal or a relevance classifier in Step 8, alongside
answer-quality eval, before this is production-trust.
