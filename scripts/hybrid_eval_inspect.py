"""Spike: diagnose where dense (HNSW) retrieval misses, tagged lexical vs semantic.

Standalone (get_connection, never the pool). V1 = dense baseline + diagnose only;
the gate decides whether the lexical + hybrid arms get built (see docs/v1/step14).

    uv run python scripts/hybrid_eval_inspect.py --book <book_id> --diagnose
"""
import argparse
import json
import os
from functools import partial
from pathlib import Path
from uuid import UUID

import numpy as np
import psycopg
from psycopg.rows import dict_row

from db.connection import get_connection
from services.chunker import Chunk
from services.embeddings import embed_query
from services.eval import run_eval
from services.generate import decide_answer
from services.retrieval import ChunkHit, search_chunks

EVAL_CASES_PATH = "eval/cases.json"
CANDIDATE_K = 20  # per-arm candidate pool fetched before RRF; report k truncates after


def load_book_chunks(conn: psycopg.Connection, book_id: UUID) -> list[Chunk]:
    """Chunks straight from the DB so chunk_index aligns with search_chunks (D2).

    The dense baseline retrieves via search_chunks (HNSW, returns DB chunk_index);
    resolve_expected must map ground truth against the *same* indices, so we read
    them from the DB rather than a local chunks.json that may have drifted.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT text, page_start, page_end, section_path, section_title, "
            "section_level, chunk_index "
            "FROM chunks WHERE book_id = %s ORDER BY chunk_index",
            (book_id,),
        ).fetchall()
    return [Chunk(**r) for r in rows]


def dense_retriever(
    conn: psycopg.Connection,
    book_id: UUID,
    query_vec: list[float],
    query_text: str,  # unused: the dense arm needs only the vector
    k: int,
) -> list[int]:
    """Production-equivalent baseline: pgvector cosine over HNSW (D2)."""
    hits = search_chunks(conn, book_id, query_vec, k)
    return [h.chunk_index for h in hits]


def lexical_retriever(
    conn: psycopg.Connection,
    book_id: UUID,
    query_vec: list[float],  # unused: the lexical arm matches text, not the vector
    query_text: str,
    k: int,
) -> list[int]:
    """A3/D3: pg_trgm word_similarity over chunks.text, book-scoped, top-k.

    word_similarity (not whole-string `<->`) ranks by how well the query matches the
    best substring of the chunk — the right signal for a short query vs a long chunk.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT chunk_index "
            "FROM chunks WHERE book_id = %s "
            "ORDER BY word_similarity(%s, text) DESC "
            "LIMIT %s",
            (book_id, query_text, k),
        ).fetchall()
    return [r["chunk_index"] for r in rows]


def rrf_fuse(rankings: list[list[int]], k: int, c: int = 60) -> list[int]:
    """Reciprocal Rank Fusion: score(idx) = Σ 1/(c + rank). No tunable weight (D4)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (c + rank)
    return sorted(scores, key=lambda i: scores[i], reverse=True)[:k]


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


def classify_miss(case: dict) -> str:
    """The lexical/semantic tag is authored on the case (eval/cases.json)."""
    return case.get("kind", "unknown")


def diagnose(
    conn: psycopg.Connection,
    book_id: UUID,
    chunks: list[Chunk],
    cases: list[dict],
    k: int = 5,
) -> None:
    retriever = partial(dense_retriever, conn, book_id)
    report = run_eval(cases, chunks, retriever, k=k)

    by_id = {c["id"]: c for c in cases}
    misses = [
        r for r in report["cases"] if not r["out_of_scope"] and not r["hit"]
    ]
    weak = [
        r
        for r in report["cases"]
        if not r["out_of_scope"] and r["hit"] and (r["first_hit_rank"] or 0) > 1
    ]

    print(
        f"\nmean Recall@{k}: {report['mean_recall_at_k']:.3f}   "
        f"mean MRR: {report['mean_mrr']:.3f}   "
        f"(dense / HNSW baseline, OOS excluded)\n"
    )

    print(f"MISSES (hit=False) — {len(misses)}:")
    for r in misses:
        print(
            f"  [{classify_miss(by_id[r['id']]):8}] {r['id']}  "
            f"expected={r['expected_indices']} top={r['top_k_indices']}  "
            f"q={r['query']!r}"
        )

    print(f"\nWEAK (hit but rank>1) — {len(weak)}:")
    for r in weak:
        print(
            f"  [{classify_miss(by_id[r['id']]):8}] rank={r['first_hit_rank']}  "
            f"{r['id']}  q={r['query']!r}"
        )

    # The gate: is there any lexical-tagged case dense fails or ranks poorly?
    lex = [r for r in misses + weak if classify_miss(by_id[r["id"]]) == "lexical"]
    print(f"\n=== GATE: {len(lex)} lexical-tagged miss/weak case(s) ===")
    print(
        "→ proceed to V2 (build pg_trgm lexical + RRF hybrid arms)"
        if lex
        else "→ hybrid NOT indicated on this set — stop; revisit chunking / reranker"
    )


def compare(
    conn: psycopg.Connection,
    book_id: UUID,
    chunks: list[Chunk],
    cases: list[dict],
    k: int = 5,
) -> None:
    arms = {
        "dense": partial(dense_retriever, conn, book_id),
        "lexical": partial(lexical_retriever, conn, book_id),
        "hybrid": partial(hybrid_retriever, conn, book_id),
    }
    reports = {name: run_eval(cases, chunks, r, k=k) for name, r in arms.items()}

    print(f"\n{'arm':8} {'Recall@' + str(k):>10} {'MRR':>8}")
    for name, rep in reports.items():
        print(f"{name:8} {rep['mean_recall_at_k']:>10.3f} {rep['mean_mrr']:>8.3f}")

    # Per-case first-hit rank per arm ('-' = miss). '*' marks where hybrid moved the
    # rank vs dense — the re-ranking signal that matters more than the mean (D5).
    by = {name: {r["id"]: r for r in rep["cases"]} for name, rep in reports.items()}
    print(f"\n{'case':9} {'kind':8} {'dense':>5} {'lex':>5} {'hyb':>5}  query")
    for c in cases:
        if c.get("out_of_scope"):
            continue
        cells = [by[a][c["id"]]["first_hit_rank"] for a in ("dense", "lexical", "hybrid")]
        d, lx, h = (str(x) if x else "-" for x in cells)
        mark = " *" if cells[2] != cells[0] else ""
        print(f"{c['id']:9} {c.get('kind', '?'):8} {d:>5} {lx:>5} {h:>5}{mark}  {c['query'][:48]}")


def hits_for_indices(
    conn: psycopg.Connection,
    book_id: UUID,
    query_vec: list[float],
    indices: list[int],
) -> list[ChunkHit]:
    """ChunkHits (with real cosine distance) for given chunk_indices, in that order.

    Lets decide_answer's refusal gate + context formatter run on the hybrid-fused set
    the same way it does on dense's search_chunks output.
    """
    if not indices:
        return []
    qv = np.asarray(query_vec, dtype=np.float32)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT c.chunk_index, c.text, c.page_start, c.page_end, c.section_path, "
            "c.section_title, c.section_level, ce.embedding <=> %s AS distance "
            "FROM chunk_embeddings ce JOIN chunks c ON c.id = ce.chunk_id "
            "WHERE c.book_id = %s AND c.chunk_index = ANY(%s)",
            (qv, book_id, list(indices)),
        ).fetchall()
    by_idx = {r["chunk_index"]: ChunkHit.model_validate(r) for r in rows}
    return [by_idx[i] for i in indices if i in by_idx]


def answer_gate(
    conn: psycopg.Connection,
    book_id: UUID,
    cases: list[dict],
    k: int = 5,
) -> None:
    """V3/D5: on cases where hybrid shifts the retrieved set, does the /ask answer
    actually change? Runs decide_answer with dense vs hybrid context, side by side."""
    floor = float(os.environ.get("ASK_SCORE_FLOOR", "0.6"))
    shifted = 0
    for c in cases:
        if c.get("out_of_scope"):
            continue
        qv = embed_query(c["query"])
        dense_idx = dense_retriever(conn, book_id, qv, c["query"], k)
        hybrid_idx = hybrid_retriever(conn, book_id, qv, c["query"], k)
        if dense_idx == hybrid_idx:
            continue
        shifted += 1
        a_d = decide_answer(c["query"], hits_for_indices(conn, book_id, qv, dense_idx), floor)
        a_h = decide_answer(c["query"], hits_for_indices(conn, book_id, qv, hybrid_idx), floor)
        print(f"\n=== {c['id']} [{c.get('kind', '?')}] {c['query']}")
        print(f"  dense  top={dense_idx}")
        print(f"  hybrid top={hybrid_idx}")
        print(f"  [dense  refused={a_d.refused}] {a_d.answer[:280]}")
        print(f"  [hybrid refused={a_h.refused}] {a_h.answer[:280]}")
    print(f"\n{shifted} shifted case(s) inspected.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, type=UUID)
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--answers", action="store_true")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    conn = get_connection()
    try:
        chunks = load_book_chunks(conn, args.book)
        cases = json.loads(Path(EVAL_CASES_PATH).read_text())
        print(f"Loaded {len(chunks)} chunks, {len(cases)} cases for book {args.book}")
        if args.diagnose:
            diagnose(conn, args.book, chunks, cases, k=args.k)
        if args.compare:
            compare(conn, args.book, chunks, cases, k=args.k)
        if args.answers:
            answer_gate(conn, args.book, cases, k=args.k)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
