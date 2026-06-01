from typing import Any
from uuid import UUID

import numpy as np
import psycopg
from psycopg.rows import dict_row

from services.types import ChunkBase


class ChunkHit(ChunkBase):
    distance: float


def search_chunks(
    conn: psycopg.Connection[Any],
    book_id: UUID,
    query_vec: list[float],
    k: int = 5,
) -> list[ChunkHit]:
    """Top-k chunks for one book by pgvector cosine distance (`<=>`), HNSW.

    query_vec must be L2-normalized (embed_query guarantees this). Uses its own
    dict_row cursor so it works under both the pooled dict_row connection (API)
    and a plain get_connection() (scripts) — independent of the connection's
    default row_factory.
    """
    # pgvector's psycopg adapter dumps numpy.ndarray as a vector literal; a
    # plain list[float] would silently go out as float8[] and break `<=>`.
    qv = np.asarray(query_vec, dtype=np.float32)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT c.chunk_index, c.text, c.page_start, c.page_end, "
            "c.section_path, c.section_title, c.section_level, "
            "ce.embedding <=> %s AS distance "
            "FROM chunk_embeddings ce "
            "JOIN chunks c ON c.id = ce.chunk_id "
            "WHERE c.book_id = %s "
            "ORDER BY ce.embedding <=> %s "
            "LIMIT %s",
            (qv, book_id, qv, k),
        ).fetchall()
    # dict_row keys match ChunkHit's fields 1:1; model_validate coerces
    # distance to float — no manual field listing.
    return [ChunkHit.model_validate(r) for r in rows]
