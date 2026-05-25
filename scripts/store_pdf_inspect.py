"""Step 4 debug: init DB, load book, eval via pgvector, compare to Step 3 baseline."""
import json
from functools import partial
from pathlib import Path

from db.connection import get_connection, init_db
from services.chunker import load_chunks
from services.embeddings import load_embeddings
from services.eval import print_report, retrieve, run_eval
from services.retrieval import retrieve_pg
from services.store import load_book

CHUNKS_PATH = "temp/chunks.json"
EMBEDDINGS_PATH = "temp/embeddings.json"
EVAL_CASES_PATH = "eval/cases.json"
BOOK_TITLE = "AI Engineering: Building Applications with Foundation Models"
BOOK_FILE = "temp/books/AI_ENGINEERING_BUILDING.pdf"


def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)
    embeddings = load_embeddings(EMBEDDINGS_PATH)
    cases = json.loads(Path(EVAL_CASES_PATH).read_text())

    init_db()
    with get_connection() as conn:
        book_id = load_book(conn, chunks, embeddings, BOOK_TITLE, BOOK_FILE)
        counts = {}
        for t in ("books", "chunks", "chunk_embeddings"):
            row = conn.execute(f"SELECT count(*) FROM {t}").fetchone()
            assert row is not None
            counts[t] = row[0]
        print(f"loaded book {book_id}: {counts}")

        report_pg = run_eval(cases, chunks, partial(retrieve_pg, conn), k=5)
        print("\n=== pgvector retrieval ===")
        print_report(report_pg)

    report_mem = run_eval(cases, chunks, partial(retrieve, embeddings), k=5)
    print("\n=== in-memory retrieval (parity reference) ===")
    print_report(report_mem)
    print("\nStep 3 baseline: Hit 8/8, Recall@5 0.590, MRR 0.729")


if __name__ == "__main__":
    main()
