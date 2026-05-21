"""Probe Gemini embed_content with varying batch sizes."""
import time

from services.embeddings import embed_batch_call, make_client

SAMPLES = ["sample text " * 50] * 100


def main() -> None:
    client = make_client()
    for n in (1, 10, 50, 100):
        batch = SAMPLES[:n]
        t0 = time.perf_counter()
        try:
            vecs = embed_batch_call(client, batch, task_type="RETRIEVAL_DOCUMENT")
            dt = time.perf_counter() - t0
            print(f"batch={n:>3}  ok  vectors={len(vecs)}  dim={len(vecs[0])}  {dt:.2f}s")
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"batch={n:>3}  FAIL  {type(e).__name__}: {e}  {dt:.2f}s")


if __name__ == "__main__":
    main()
