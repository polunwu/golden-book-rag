---
shaping: false
---

# Probe Inspection Notes: `scripts/probe_pgvector.py`

Date run: 2026-05-25
Postgres: `pgvector/pgvector:pg17` via docker compose (volume `bookrag_pgdata`)
pgvector extension: 0.8.2
Python adapter: `pgvector==0.4.2`, `psycopg[binary]==3.3.4`

## Setup

- `init_db()` applies `db/schema.sql` (creates `vector` extension + 3 tables + HNSW index)
- Probe creates a TEMP table `_probe (id int, embedding vector(1536))` + HNSW index over `vector_cosine_ops`
- Inserts 200 rows of N(0,1) random vectors (dim 1536, dtype float32)
- Queries `ORDER BY embedding <=> %s LIMIT 5` against `rows[0]`
- `SET LOCAL enable_seqscan = off` to force planner toward the index path
- Verifies: (a) extension present, (b) `Index Scan using _probe_embedding_idx` in EXPLAIN, (c) self-hit at rank 1

## Result

```
pgvector extension: 0.8.2
HNSW index usable by <=>: True
nearest to row 0: [0, 122, 158, 1, 195]  (self-hit rank 1: True)
```

## Headline

- pgvector + HNSW wiring works end-to-end with the psycopg adapter.
- Index is *used* by the planner for `<=>` (cosine distance).
- Self-hit at rank 1 confirms distance semantics.

## Two non-obvious gotchas hit during this probe

Both bit hard enough to be worth capturing in [[pgvector-psycopg-dumper]] and
[[hnsw-index-auto-naming]] (project memory).

**1. `register_vector` does NOT dump `list[float]` as `vector`.**

pgvector 0.4.2's `register_vector(conn)` registers psycopg dumpers ONLY for
`numpy.ndarray` and `pgvector.Vector`. A plain `list[float]` parameter is
dumped by psycopg's default rule as `double precision[]`, producing:

```
operator does not exist: vector <=> double precision[]
```

Fix: all embedding values passed as psycopg parameters in this project go
through `np.asarray(vec, dtype=np.float32)` — see `services/retrieval.py`
`retrieve_pg` and `services/store.py` `load_book`. The probe does the same in
`_rand_vec()`.

**2. Auto-named HNSW indexes contain no "hnsw" in the EXPLAIN plan.**

`CREATE INDEX ON _probe USING hnsw (embedding vector_cosine_ops)` without an
explicit name produces `_probe_embedding_idx`. The plan prints
`Index Scan using _probe_embedding_idx` — the access-method name "hnsw" never
appears. Initial probe check `'hnsw' in plan_text.lower()` printed `False`
even though the index WAS being used. Fix: check for `Index Scan` + the
specific index name.

## Not Tested

- **Pool / concurrency.** Single-connection probe only. Step 5 swaps `get_connection`
  for `psycopg_pool` — pool behavior with `register_vector` per checkout is untested.
- **HNSW recall at production scale.** 200 random vectors is a smoke test; the real
  parity signal is `store_pdf_inspect.py` on 1286 chunks (see store-inspection-notes.md).
- **HNSW build parameters.** Index created with defaults (`m=16`, `ef_construction=64`).
  Not tuned.
- **`SET LOCAL enable_seqscan = off` necessity.** With 200 rows, the planner *might*
  pick the index on its own — not measured. The override exists to guarantee a clean
  probe signal, not because it's required in production.

## Re-run Triggers

Re-run this probe if any of these change:

- `pgvector` extension version bump (e.g., 0.8.x → 0.9.x)
- `pgvector` Python adapter or `psycopg` bump
- Postgres major version bump (pg17 → pg18)
- Switching DB host (managed Postgres, RDS, Supabase) — extension availability + version
- HNSW build parameters changed in `db/schema.sql`
- `register_vector` call site moves (e.g., into a pool factory)

## Decision

pgvector + HNSW + psycopg adapter wired correctly. Proceed to
`scripts/store_pdf_inspect.py` for end-to-end parity against Step 3.
