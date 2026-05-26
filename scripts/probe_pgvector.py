"""Probe pgvector: extension, vector round-trip, <=> ordering, HNSW index usability."""
import random

import numpy as np
from psycopg import sql

from db.connection import get_connection
from services.embeddings import EMBEDDING_DIM


def _rand_vec() -> np.ndarray:
    return np.asarray(
        [random.gauss(0.0, 1.0) for _ in range(EMBEDDING_DIM)],
        dtype=np.float32,
    )


def main() -> None:
    with get_connection() as conn:
        ver = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        print(f"pgvector extension: {ver[0] if ver else 'MISSING'}")

        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE TEMP TABLE _probe (id int, embedding vector({}))").format(
                    sql.Literal(EMBEDDING_DIM)
                )
            )
            cur.execute("CREATE INDEX ON _probe USING hnsw (embedding vector_cosine_ops)")
            rows = [(i, _rand_vec()) for i in range(200)]
            cur.executemany("INSERT INTO _probe VALUES (%s, %s)", rows)

            probe_id, probe_vec = rows[0]
            cur.execute("SET LOCAL enable_seqscan = off")
            plan = cur.execute(
                "EXPLAIN SELECT id FROM _probe ORDER BY embedding <=> %s LIMIT 5",
                (probe_vec,),
            ).fetchall()
            plan_text = "\n".join(r[0] for r in plan)
            # HNSW index on `_probe.embedding` is auto-named (no "hnsw" in the
            # name) — confirm via Index Scan on the column's only index instead.
            uses_index = "Index Scan" in plan_text and "_probe_embedding_idx" in plan_text
            print(f"HNSW index usable by <=>: {uses_index}")

            top = cur.execute(
                "SELECT id FROM _probe ORDER BY embedding <=> %s LIMIT 5",
                (probe_vec,),
            ).fetchall()
            print(f"nearest to row {probe_id}: {[r[0] for r in top]}  "
                  f"(self-hit rank 1: {top[0][0] == probe_id})")


if __name__ == "__main__":
    main()
