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


def ingest_book(
    conn: psycopg.Connection,
    book_id: uuid.UUID,
    chunks: list[Chunk],
    embeddings: list[Embedding],
    title: str,
    file_path: str,
) -> uuid.UUID:
    """Per-book ingest. Single transaction:
      1. UPSERT books row (id-keyed)
      2. DELETE FROM chunks WHERE book_id = ?  (CASCADEs chunk_embeddings)
      3. INSERT chunks + chunk_embeddings for this book

    Idempotent per book_id. Does NOT touch other books' rows. Does NOT write
    books.status — V3's orchestrator owns the pending/processing/ready/failed
    lifecycle; V1 callers leave status at its default ('pending').
    """
    _assert_index_parity(chunks, embeddings)
    id_by_index = {c["chunk_index"]: uuid.uuid4() for c in chunks}

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO books (id, title, file_path) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, "
            "file_path = EXCLUDED.file_path",
            (book_id, title, file_path),
        )
        # CASCADE FK (rev _chunks_cascade) removes chunk_embeddings rows.
        cur.execute("DELETE FROM chunks WHERE book_id = %s", (book_id,))
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
