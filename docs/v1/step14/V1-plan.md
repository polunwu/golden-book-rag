---
shaping: true
---

# Step 14 · V1 — Adequate eval set + diagnose (gate) — Implementation Plan

Implements V1 of the Step 14 slices (`docs/v1/step14/slices.md`): an **adequate**
eval set + the **production-equivalent dense baseline** (HNSW) + the **diagnose**
run that tags where pure-dense misses. This is the **D1 stop/go gate** — its output
decides whether V2 (lexical + hybrid) is built at all. **No pg_trgm, no hybrid, no
answer gate** in V1. Standalone spike, run against one real `ready` book.

Reuses, unchanged: `services.eval.run_eval` *(one-line widened, below)*,
`resolve_expected`, `recall_at_k`, `mrr`, `print_report`; `services.retrieval.
search_chunks`; `services.embeddings.embed_query`; `db.connection.get_connection`;
the `services.chunker.Chunk` TypedDict; the `scripts/*_inspect.py` standalone idiom
(`get_connection()`, never the pool).

> ⚠️ **Two grounding facts that shape V1** (verified against the code):
> 1. **The existing eval flow is file-based, not DB-based.** `scripts/embed_pdf_
>    inspect.py` loads chunks from `temp/chunks.json` and runs `partial(retrieve,
>    embeddings)` (in-memory exact dot-product). V1's baseline must be **`search_
>    chunks` (HNSW, in the DB)** per D2, so V1 **loads chunks from the DB** for the
>    book — that guarantees the `chunk_index`es passed to `resolve_expected` align
>    with what `search_chunks` returns. (Loading from `temp/chunks.json` would only
>    align if that file is exactly what was ingested — fragile; don't.)
> 2. **Widening `run_eval` ripples to the existing `retrieve()`.** `run_eval` will
>    call `retriever(qv, case["query"], k)`. The current in-memory `retrieve(embeddings,
>    query_vec, k)` (still used by `embed_pdf_inspect.py` via `partial`) **must gain
>    the ignored text param** or that driver breaks. V1 widens both.

## Files

| File | Change |
|------|--------|
| `services/eval.py` | **Widen** `Retriever` type → `Callable[[list[float], str, int], list[int]]`; `run_eval` call site → `retriever(qv, case["query"], k)`; **widen `retrieve()`** to accept (and ignore) a `query_text` param; **add** optional `kind` to `EvalCase` |
| `eval/cases.json` | **Extend** to ~25–40 scored cases across the 6 R4.1 strata; tag every case (old + new) with `kind: "semantic" \| "lexical"` |
| `scripts/hybrid_eval_inspect.py` | **New** — the driver: `get_connection`, `load_book_chunks(conn, book_id)`, `dense_retriever`, `diagnose()`, `classify_miss`, tagged-miss print + gate verdict |

No new migration in V1 (pg_trgm is V2). No production request-path change (R6.1).

## Steps

### 1. Widen the harness (`services/eval.py`) — N10, EvalCase

The breadboard's key finding: the lexical arm (V2) needs the **query text**, which
`run_eval` never passes. Make the signature carry it now so it's stable from V1.

```python
# type alias — add the query string
Retriever = Callable[[list[float], str, int], list[int]]

# run_eval: the ONE-LINE change at the call site
qv = embed_query(case["query"])
top = retriever(qv, case["query"], k)   # was: retriever(qv, k)

# retrieve(): the in-memory exact retriever keeps working — add an ignored param
def retrieve(
    embeddings: list[Embedding],
    query_vec: list[float],
    query_text: str,            # NEW — ignored (dense arm); keeps run_eval's call uniform
    k: int = 5,
) -> list[int]:
    ...                          # body unchanged

# EvalCase: add the gate tag (TypedDict is total=False, so it's optional)
class EvalCase(TypedDict, total=False):
    id: str
    query: str
    expected_page_start: int
    expected_page_end: int
    expected_section_substring: str
    expected_keywords: list[str]
    out_of_scope: bool
    kind: str                    # NEW — "semantic" | "lexical" (drives the gate)
```

- Scoring / OOS / `resolve_expected` logic **untouched**.
- `embed_pdf_inspect.py` is unaffected: `partial(retrieve, embeddings)` →
  `retrieve(embeddings, qv, query_text, k)`; the new param is absorbed positionally.
- `kind` is read only by the diagnose tagger (step 4). Absent ⇒ treat as unknown.

### 2. Extend the case set (`eval/cases.json`) — S3, R4.1/D6

Author against **one** ingested, `ready` book (use its `chunks` as the GT surface —
read them via `make db-shell` or the loader in step 3). Grow from 11 → ~25–40
scored cases. Tag **every** case with `kind`.

- **Existing 11** → `kind: "semantic"` (the paraphrase/conceptual stratum). Keep
  as-is otherwise.
- **Add `kind: "lexical"` cases** across the strata (≥1–2 each, both languages):
  | Stratum | Example shape |
  |---------|---------------|
  | (i) rare proper noun / name | a person/place/product named once in the book, quoted verbatim |
  | (ii) book-specific exact term | a low-frequency term-of-art, exact spelling |
  | (iii) number / equation / identifier | a specific metric value, formula token, code id |
  | (iv) exact-phrase / verbatim quote | a short literal phrase lifted from a chunk |
  | (v) CJK exact term | a specific 中文 term appearing verbatim |
  | (vi) misspelled / near-form | a deliberately mistyped version of (i)/(ii) — kept because D3=pg_trgm tolerates trigram near-matches |
- Each case keeps the durable-GT contract: `expected_page_start/end` +
  `expected_section_substring` (resolved at run time by `resolve_expected`). **Verify
  each new case resolves to ≥1 chunk** — `run_eval` raises if a non-OOS case
  resolves to 0 (`eval.py:89`).

### 3. The driver scaffold (`scripts/hybrid_eval_inspect.py`) — N1, N2, N5, N20

```python
"""Spike: diagnose where dense (HNSW) retrieval misses, tagged lexical vs semantic.

Standalone (get_connection, never the pool). V1 = dense baseline + diagnose only.
"""
import argparse
import json
from functools import partial
from pathlib import Path
from uuid import UUID

import numpy as np
from psycopg.rows import dict_row

from db.connection import get_connection
from services.chunker import Chunk
from services.eval import run_eval
from services.retrieval import search_chunks

EVAL_CASES_PATH = "eval/cases.json"


def load_book_chunks(conn, book_id: UUID) -> list[Chunk]:
    """Chunks straight from the DB so chunk_index aligns with search_chunks (D2)."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT text, page_start, page_end, section_path, section_title, "
            "section_level, chunk_index "
            "FROM chunks WHERE book_id = %s ORDER BY chunk_index",
            (book_id,),
        ).fetchall()
    return [Chunk(**r) for r in rows]


def dense_retriever(conn, book_id: UUID, query_vec: list[float], query_text: str, k: int) -> list[int]:
    """A2/D2: production HNSW. Ignores query_text (the dense arm needs only the vector)."""
    hits = search_chunks(conn, book_id, query_vec, k)
    return [h.chunk_index for h in hits]
```

- `dense_retriever` matches the widened `Retriever` sig; `query_text` ignored.
- Bind per book with `partial(dense_retriever, conn, book_id)` (N20) before passing
  to `run_eval`.

### 4. Diagnose + gate (`scripts/hybrid_eval_inspect.py`) — N3, N4, U2

```python
def classify_miss(case: dict) -> str:
    # N4: the tag is authored on the case (step 2). Coarse: lexical vs semantic.
    return case.get("kind", "unknown")


def diagnose(conn, book_id: UUID, chunks: list[Chunk], cases: list[dict], k: int = 5) -> None:
    retriever = partial(dense_retriever, conn, book_id)
    report = run_eval(cases, chunks, retriever, k=k)

    by_id = {c["id"]: c for c in cases}
    misses = [r for r in report["cases"] if not r["out_of_scope"] and not r["hit"]]
    weak = [r for r in report["cases"]
            if not r["out_of_scope"] and r["hit"] and (r["first_hit_rank"] or 0) > 1]

    print(f"\nmean Recall@{k}: {report['mean_recall_at_k']:.3f}   "
          f"mean MRR: {report['mean_mrr']:.3f}   (dense/HNSW baseline, OOS excluded)\n")

    print("MISSES (hit=False):")
    for r in misses:
        print(f"  [{classify_miss(by_id[r['id']]):8}] {r['id']}  "
              f"expected={r['expected_indices']} top={r['top_k_indices']}  q={r['query']!r}")
    print("\nWEAK (hit but rank>1):")
    for r in weak:
        print(f"  [{classify_miss(by_id[r['id']]):8}] rank={r['first_hit_rank']}  "
              f"{r['id']}  q={r['query']!r}")

    # THE GATE (D1)
    lex_misses = [r for r in misses + weak if classify_miss(by_id[r["id"]]) == "lexical"]
    print(f"\n=== GATE: {len(lex_misses)} lexical-tagged miss/weak case(s) ===")
    print("→ proceed to V2 (build lexical + hybrid)" if lex_misses
          else "→ hybrid NOT indicated on this set — stop; revisit chunking/reranker")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, type=UUID)
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    conn = get_connection()
    try:
        chunks = load_book_chunks(conn, args.book)
        cases = json.loads(Path(EVAL_CASES_PATH).read_text())
        print(f"Loaded {len(chunks)} chunks, {len(cases)} cases for book {args.book}")
        if args.diagnose:
            diagnose(conn, args.book, chunks, cases, k=args.k)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- **Diagnose reads both true misses *and* "weak" hits (rank > 1)** — a lexical case
  that dense ranks 4th is still signal that lexical fusion could lift it.
- The **gate** keys off the authored `kind` tag, not a fragile runtime heuristic:
  the case author already knows whether a case stresses lexical recall (step 2).
- `query_vec` flows as `np.ndarray` inside `search_chunks` already (it wraps the
  list) — the driver passes the plain list `embed_query` returns; no adapter
  concern here (that lives in `search_chunks`).

## Demo / acceptance

```
make db-up && make db-migrate          # pgvector up, schema current
# ingest one real PDF via the API, wait for status=ready; note its book_id
# extend eval/cases.json against that book (step 2)
uv run python scripts/hybrid_eval_inspect.py --book <book_id> --diagnose
```

1. Prints chunk + case counts, then the **dense/HNSW** mean Recall@k / MRR.
2. Prints a **MISSES** list and a **WEAK (rank>1)** list, each line tagged
   `[lexical]` / `[semantic]`.
3. Prints the **GATE** line: *N lexical-tagged misses → proceed to V2* **or**
   *hybrid not indicated → stop*.
4. `run_eval` does **not** raise (every non-OOS case resolves to ≥1 chunk — fix any
   that don't in step 2).
5. No DB writes, no production path touched; `embed_pdf_inspect.py` still runs
   (widened `retrieve` signature is backward-compatible via `partial`).

**Gate outcome decides V2.** Record the result in `inspection-notes.md` (dated).
If the gate says *proceed*, write `V2-plan.md` (pg_trgm migration + lexical/hybrid
retrievers + three-arm `compare()`). If *stop*, the spike ends here with the
finding — hybrid is not the lever; revisit chunking or a reranker (out of Step 14).

## Out of V1 (later slices)

- **pg_trgm migration + lexical arm + RRF hybrid + three-arm comparison** → V2.
- **`/ask` answer gate (dense vs hybrid) + written go/no-go verdict** → V3.
- **Wiring hybrid into `search_chunks` / `/ask`** → conditional follow-up step, only
  if V3's verdict is "ship" (R6.1).
