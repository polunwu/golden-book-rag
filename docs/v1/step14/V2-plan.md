---
shaping: true
---

# Step 14 · V2 — Lexical (pg_trgm) + RRF hybrid + three-arm comparison — Implementation Plan

Implements V2 of the Step 14 slices (`docs/v1/step14/slices.md`), built because
**V1's gate cleared** (2026-06-12: 3 lexical-tagged miss/weak cases; dense baseline
Recall@5 0.526, MRR 0.766 — see `inspection-notes.md`). Adds the **pg_trgm lexical
arm**, the **RRF hybrid arm**, and the **three-arm comparison**. No answer gate (V3),
no production retrieval change (R6.1).

Reuses, unchanged from V1: the widened `Retriever` sig + `run_eval` / `print_report`
(`services/eval.py`), `dense_retriever` / `load_book_chunks` / the driver scaffold
(`scripts/hybrid_eval_inspect.py`), `search_chunks`, the extended `eval/cases.json`.

> ⚠️ **Operator correction vs. the breadboard.** Breadboard finding #2 said "try
> `text <-> %s` first." That's wrong for this shape: `<->` is **whole-string**
> trigram distance, so a short query vs. a long chunk scores ~0 (the chunk's many
> non-query trigrams dominate). Use **`word_similarity(query, text)`** — how well
> the query matches the *best substring* of the chunk. Primary ranking:
> `ORDER BY word_similarity(%s, text) DESC`.

> ⚠️ **Index vs. scale.** GIN `gin_trgm_ops` accelerates the boolean trigram
> operators (`%`, `<%`), **not** KNN `ORDER BY`. At spike scale (~1286 chunks,
> book-scoped) the lexical query will likely **seq-scan that book's rows and rank
> in memory — which is fine** (trivially cheap). Create the index anyway as the
> production-shaped artifact; just don't expect/force the planner to use it for the
> ORDER BY at this size (breadboard finding #3's `EXPLAIN` check becomes "confirm
> the book-scoped scan is cheap," not "confirm GIN KNN").

## Files

| File | Change |
|------|--------|
| `alembic/versions/<rev>_pg_trgm_index.py` | **New** migration — `CREATE EXTENSION IF NOT EXISTS pg_trgm` + GIN `gin_trgm_ops` index on `chunks.text`; `down_revision = '6f01c766ea52'` |
| `scripts/hybrid_eval_inspect.py` | **Add** `lexical_retriever`, `rrf_fuse`, `hybrid_retriever`, `compare()`, a `--compare` flag, and `CANDIDATE_K` |

No `services/eval.py` change (the widening landed in V1). No request-path change.

## Steps

### 1. Migration — pg_trgm extension + GIN index (N30)

`uv run alembic revision -m "pg_trgm_index"`, then hand-write (autogenerate isn't
wired — raw SQL via `op.execute`, matching the existing migrations):

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX chunks_text_trgm_idx ON chunks USING gin (text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_text_trgm_idx")
    # leave the extension installed (other things may rely on it); drop only if needed:
    # op.execute("DROP EXTENSION IF EXISTS pg_trgm")
```

- Set `down_revision = '6f01c766ea52'` (current head, `book_status`).
- Apply with `make db-migrate`. `CREATE EXTENSION` needs superuser — the dev
  container's default `postgres` role has it; note in the demo if a managed prod DB
  would need it pre-installed.

### 2. Lexical retriever — pg_trgm word_similarity (N6, N22)

In `scripts/hybrid_eval_inspect.py`. Uses the **query text** (the reason for V1's
widening); ignores the vector. `psycopg.sql` not needed — these are bound params,
not dynamic identifiers (no f-string SQL).

```python
def lexical_retriever(
    conn: psycopg.Connection,
    book_id: UUID,
    query_vec: list[float],   # unused: the lexical arm matches text
    query_text: str,
    k: int,
) -> list[int]:
    """A3/D3: pg_trgm word_similarity over chunks.text, book-scoped, top-k."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT chunk_index "
            "FROM chunks WHERE book_id = %s "
            "ORDER BY word_similarity(%s, text) DESC "
            "LIMIT %s",
            (book_id, query_text, k),
        ).fetchall()
    return [r["chunk_index"] for r in rows]
```

- `word_similarity(%s, text) DESC` ranks chunks by how well the query matches a
  substring of the chunk — the right signal for short query → long chunk.
- Book-scoped `WHERE book_id=%s` keeps it to one book's chunks (~1286), so the
  in-memory rank is cheap regardless of index use.

### 3. RRF fusion + hybrid retriever (N7, N8)

```python
CANDIDATE_K = 20  # fetch wide per arm before fusing; report k truncates after


def rrf_fuse(rankings: list[list[int]], k: int, c: int = 60) -> list[int]:
    """Reciprocal Rank Fusion: score(idx) = Σ 1/(c + rank). No tunable weight (D4)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (c + rank)
    ranked = sorted(scores, key=lambda i: scores[i], reverse=True)
    return ranked[:k]


def hybrid_retriever(
    conn: psycopg.Connection,
    book_id: UUID,
    query_vec: list[float],
    query_text: str,
    k: int,
) -> list[int]:
    """A4/D4: RRF over dense (HNSW) + lexical (pg_trgm), each fetched wide."""
    dense = dense_retriever(conn, book_id, query_vec, query_text, CANDIDATE_K)
    lexical = lexical_retriever(conn, book_id, query_vec, query_text, CANDIDATE_K)
    return rrf_fuse([dense, lexical], k=k)
```

- **Fetch wide (CANDIDATE_K=20), fuse, then cut to `k`** (breadboard finding #4) —
  pulling only top-5 per arm before RRF starves the fusion.
- `c=60` is the conventional RRF constant; nothing to tune (the D4 point).

### 4. Three-arm comparison + per-case deltas (N11, N12, U3)

```python
def compare(conn, book_id, chunks, cases, k=5) -> None:
    arms = {
        "dense":   partial(dense_retriever, conn, book_id),
        "lexical": partial(lexical_retriever, conn, book_id),
        "hybrid":  partial(hybrid_retriever, conn, book_id),
    }
    reports = {name: run_eval(cases, chunks, r, k=k) for name, r in arms.items()}

    # Means table
    print(f"\n{'arm':8} {'Recall@'+str(k):>10} {'MRR':>8}")
    for name, rep in reports.items():
        print(f"{name:8} {rep['mean_recall_at_k']:>10.3f} {rep['mean_mrr']:>8.3f}")

    # Per-case rank deltas (rank of first hit per arm; '-' = miss). Highlight where
    # hybrid changes the dense rank — the signal that matters more than the mean (D5).
    by = {name: {r["id"]: r for r in rep["cases"]} for name, rep in reports.items()}
    print(f"\n{'case':9} {'kind':8} {'dense':>5} {'lex':>5} {'hyb':>5}  query")
    for c in cases:
        if c.get("out_of_scope"):
            continue
        cells = [by[a][c["id"]]["first_hit_rank"] for a in ("dense", "lexical", "hybrid")]
        d, l, h = (str(x) if x else "-" for x in cells)
        mark = " *" if cells[2] != cells[0] else ""   # hybrid moved vs dense
        print(f"{c['id']:9} {c.get('kind','?'):8} {d:>5} {l:>5} {h:>5}{mark}  {c['query'][:48]}")
```

Wire `--compare` in `main()` alongside `--diagnose`:

```python
ap.add_argument("--compare", action="store_true")
...
if args.compare:
    compare(conn, args.book, chunks, cases, k=args.k)
```

- `run_eval` re-embeds each query 3× (once per arm). Acceptable for a spike; if the
  Gemini cost grates, cache `embed_query` results by query string in the driver
  (out of scope unless it hurts).

## Demo / acceptance

```
make db-migrate    # applies the pg_trgm migration (extension + GIN index)
uv run python scripts/hybrid_eval_inspect.py --book 652cca68-... --compare
```

1. A **means table**: dense / lexical / hybrid Recall@5 + MRR. Dense row should
   match V1 (0.526 / 0.766) — a sanity check the harness is unchanged.
2. A **per-case rank table**: dense/lex/hyb first-hit rank per case, `*` where
   hybrid moved the rank vs dense. Read **case-13 (LoRA)** — does lexical/hybrid
   recover the miss? And **case-14 (MMLU, dense rank 4)** — does hybrid lift it?
3. **CJK cross-lingual sanity (V1 finding #1):** cases 08/10/11/12 (中文 query →
   English text) should show lexical ≈ miss (near-zero trigram overlap), so hybrid
   ≈ dense there. Confirm the lexical column is `-`/poor on those — expected, not a
   bug.
4. `EXPLAIN (ANALYZE)` one lexical query (optional) — confirm the book-scoped scan
   is cheap; don't force GIN KNN (see warning).
5. No request-path code touched; `--diagnose` still works.

Record the three-arm numbers + notable rank movements in `inspection-notes.md`
(dated). These feed V3's verdict.

## Out of V2 (later)

- **`/ask` answer gate (dense vs hybrid context) + written go/no-go verdict** → V3.
- **`word_similarity` threshold / `strict_word_similarity` / GiST KNN tuning** — only
  if lexical recall looks weak at spike scale; not needed to get the comparison.
- **Weighted score fusion** — RRF first; revisit only if it leaves clear signal
  (D4).
- **Wiring hybrid into `search_chunks` / `/ask`** — conditional follow-up, only if
  V3 says "ship" (R6.1).
