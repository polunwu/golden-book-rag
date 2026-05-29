"""Step 4 debug, V1-flavoured: load via ingest_book (fixed book_id), parity-check."""
import json
import uuid
from functools import partial
from pathlib import Path

from db.connection import get_connection
from services.chunker import load_chunks
from services.embeddings import load_embeddings
from services.eval import print_report, retrieve, run_eval
from services.retrieval import search_chunks
from services.store import ingest_book

CHUNKS_PATH = "temp/chunks.json"
EMBEDDINGS_PATH = "temp/embeddings.json"
EVAL_CASES_PATH = "eval/cases.json"
BOOK_TITLE = "AI Engineering: Building Applications with Foundation Models"
BOOK_FILE = "temp/books/AI_ENGINEERING_BUILDING.pdf"
# Fixed UUID → re-running this script re-ingests the same book row.
BOOK_ID = uuid.UUID("00000000-0000-0000-0000-00000000a1e0")


def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)
    embeddings = load_embeddings(EMBEDDINGS_PATH)
    cases = json.loads(Path(EVAL_CASES_PATH).read_text())

    with get_connection() as conn:
        book_id = ingest_book(conn, BOOK_ID, chunks, embeddings, BOOK_TITLE, BOOK_FILE)
        counts = {}
        for t in ("books", "chunks", "chunk_embeddings"):
            row = conn.execute(f"SELECT count(*) FROM {t}").fetchone()
            assert row is not None
            counts[t] = row[0]
        print(f"ingested book {book_id}: {counts}")

        def pg_retriever(qv: list[float], k: int) -> list[int]:
            return [h.chunk_index for h in search_chunks(conn, BOOK_ID, qv, k)]

        report_pg = run_eval(cases, chunks, pg_retriever, k=5)
        print("\n=== pgvector retrieval ===")
        print_report(report_pg)

    report_mem = run_eval(cases, chunks, partial(retrieve, embeddings), k=5)
    print("\n=== in-memory retrieval (parity reference) ===")
    print_report(report_mem)
    print("\nStep 3 baseline: Hit 8/8, Recall@5 0.590, MRR 0.729")


if __name__ == "__main__":
    main()
