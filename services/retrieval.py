import numpy as np
import psycopg


def retrieve_pg(
    conn: psycopg.Connection,
    query_vec: list[float],
    k: int = 5,
) -> list[int]:
    """Top-k chunk_index by cosine distance via pgvector. query_vec must be
    L2-normalized — embed_query already guarantees this."""
    # pgvector's psycopg adapter only registers dumpers for numpy.ndarray /
    # pgvector.Vector, not plain list[float] — convert to keep <=> typed.
    qv = np.asarray(query_vec, dtype=np.float32)
    rows = conn.execute(
        "SELECT c.chunk_index "
        "FROM chunk_embeddings ce "
        "JOIN chunks c ON c.id = ce.chunk_id "
        "ORDER BY ce.embedding <=> %s "
        "LIMIT %s",
        (qv, k),
    ).fetchall()
    return [r[0] for r in rows]
