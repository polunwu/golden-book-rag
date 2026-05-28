"""Background ingest orchestrator. Owns books.status lifecycle.

Pure sync code (ingest_pdf) wrapped in an async thread-offload (run_ingest).
Imported by api/routers/books.py — must NOT import from api.* (R3.2).
"""
import logging
import uuid

from anyio import to_thread

from db.connection import get_pool
from services.chunker import chunk_pdf
from services.embeddings import embed_chunks
from services.pdf_parser import open_pdf
from services.store import ingest_book

log = logging.getLogger(__name__)


def _set_status(
    book_id: uuid.UUID, status: str, error_message: str | None = None
) -> None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE books SET status = %s::book_status, error_message = %s "
                "WHERE id = %s",
                (status, error_message, book_id),
            )
        conn.commit()


def ingest_pdf(book_id: uuid.UUID, pdf_path: str, title: str) -> None:
    try:
        _set_status(book_id, "processing")
        doc = open_pdf(pdf_path)
        chunks = chunk_pdf(doc)
        embeddings = embed_chunks(chunks)
        with get_pool().connection() as conn:
            ingest_book(conn, book_id, chunks, embeddings, title, pdf_path)
        _set_status(book_id, "ready")
    except Exception as exc:
        # Fresh conn — the ingest_book conn may be in aborted-tx state.
        log.exception("ingest failed book_id=%s", book_id)
        _set_status(book_id, "failed", str(exc)[:2000])


async def run_ingest(book_id: uuid.UUID, pdf_path: str, title: str) -> None:
    await to_thread.run_sync(ingest_pdf, book_id, pdf_path, title)
