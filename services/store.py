import uuid

import numpy as np
import psycopg

from services.chunker import Chunk
from services.embeddings import Embedding


def _assert_index_parity(chunks: list[Chunk], embeddings: list[Embedding]) -> None:
    cidx = {c["chunk_index"] for c in chunks}
    eidx = {e["chunk_index"] for e in embeddings}
    if cidx != eidx:
        raise ValueError(
            f"chunk_index mismatch — chunks-only={sorted(cidx - eidx)[:5]}, "
            f"embeddings-only={sorted(eidx - cidx)[:5]}"
        )


def load_book(
    conn: psycopg.Connection,
    chunks: list[Chunk],
    embeddings: list[Embedding],
    title: str,
    file_path: str,
) -> uuid.UUID:
    """Full refresh: truncate, then insert one book + all chunks + all embeddings.
    Idempotent — re-running fully replaces prior data."""
    _assert_index_parity(chunks, embeddings)

    book_id = uuid.uuid4()
    id_by_index = {c["chunk_index"]: uuid.uuid4() for c in chunks}

    with conn.cursor() as cur:
        # Single-book MVP: full wipe + reload. Step 5 (multi-book upload) MUST
        # replace this with per-book scoped ops — TRUNCATE destroys other books
        # and locks whole tables. See shaping.md Step 5 Hand-off.
        cur.execute("TRUNCATE books, chunks, chunk_embeddings CASCADE")
        cur.execute(
            "INSERT INTO books (id, title, file_path) VALUES (%s, %s, %s)",
            (book_id, title, file_path),
        )
        cur.executemany(
            "INSERT INTO chunks (id, book_id, text, page_start, page_end, "
            "section_path, section_title, section_level, chunk_index) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    id_by_index[c["chunk_index"]], book_id, c["text"],
                    c["page_start"], c["page_end"], c["section_path"],
                    c["section_title"], c["section_level"], c["chunk_index"],
                )
                for c in chunks
            ],
        )
        cur.executemany(
            "INSERT INTO chunk_embeddings (chunk_id, embedding, embedding_model) "
            "VALUES (%s, %s, %s)",
            [
                (
                    id_by_index[e["chunk_index"]],
                    np.asarray(e["vector"], dtype=np.float32),
                    e["embedding_model"],
                )
                for e in embeddings
            ],
        )
    conn.commit()
    return book_id
