"""Step 3 debug: embed chunks, save, run eval."""
import json
from pathlib import Path

from services.chunker import load_chunks
from services.embeddings import embed_chunks, load_embeddings, save_embeddings
from services.eval import print_report, run_eval

CHUNKS_PATH = "temp/chunks.json"
EMBEDDINGS_PATH = "temp/embeddings.json"
EVAL_CASES_PATH = "eval/cases.json"


def main() -> None:
    chunks = load_chunks(CHUNKS_PATH)
    print(f"Loaded {len(chunks)} chunks")

    embeddings = embed_chunks(chunks)
    save_embeddings(embeddings, EMBEDDINGS_PATH)
    print(f"Saved {len(embeddings)} embeddings to {EMBEDDINGS_PATH}")

    reloaded = load_embeddings(EMBEDDINGS_PATH)
    assert len(reloaded) == len(embeddings)

    cases = json.loads(Path(EVAL_CASES_PATH).read_text())
    report = run_eval(cases, chunks, reloaded, k=5)
    print_report(report)


if __name__ == "__main__":
    main()
