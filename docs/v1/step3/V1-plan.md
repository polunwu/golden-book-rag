---
shaping: true
---

# Step 3: V1 Implementation Plan — Chunks → Embeddings + Eval

Implements **Shape B: Batched embedding pipeline + reusable eval harness** (see [shaping.md](./shaping.md), constants from [spike-batch-size.md](./spike-batch-size.md)).

## Files

| File                              | Action                |
| --------------------------------- | --------------------- |
| `pyproject.toml`                  | Add deps              |
| `.env.example`                    | Create                |
| `.gitignore`                      | Ensure `.env`, `temp/`|
| `services/embeddings.py`          | Create                |
| `services/eval.py`                | Create                |
| `scripts/probe_gemini_batch.py`   | Create (run once)     |
| `scripts/embed_pdf_inspect.py`    | Create                |
| `temp/eval_cases.json`            | Hand-curate           |

---

## 1. Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    "pymupdf>=1.27.2.3",
    "google-genai>=1.0",
    "tenacity>=9.0",
    "python-dotenv>=1.0",
    "numpy>=2.0",
]
```

Run `uv sync` after edit.

---

## 2. `.env` handling

`.env.example`:

```text
GEMINI_API_KEY=
```

Ensure `.gitignore` contains `.env` (and `temp/` already covers embeddings.json).

`services/embeddings.py` loads via `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv()  # idempotent; reads .env into os.environ if present

if not os.environ.get("GEMINI_API_KEY"):
    raise RuntimeError("GEMINI_API_KEY missing — set in .env or environment")
```

The `genai.Client()` constructor auto-picks up `GEMINI_API_KEY` from env.

---

## 3. Constants + `Embedding` TypedDict

In `services/embeddings.py`:

```python
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 1536
EMBED_TOKEN_BUDGET = 18_000    # 90% of Vertex-documented 20K cap
EMBED_BATCH_HARD_CAP = 100     # belt + suspenders
PER_TEXT_TOKEN_CAP = 2_048     # Gemini model card
TOKENS_PER_CHAR = 0.25         # heuristic: ~4 chars/token for English

class Embedding(TypedDict):
    chunk_index: int
    vector: list[float]
    embedding_model: str
```

---

## 4. Token counting helper

Cheap heuristic — avoids extra API call:

```python
def _est_tokens(text: str) -> int:
    return max(1, int(len(text) * TOKENS_PER_CHAR))
```

For precise counts later (e.g., during retrieval), can swap to `client.models.count_tokens(model=..., contents=text)`.

---

## 5. Pre-flight assert (B1.3 / R3.4)

```python
def _check_chunk_sizes(chunks: list[Chunk]) -> None:
    for c in chunks:
        if _est_tokens(c["text"]) > PER_TEXT_TOKEN_CAP:
            raise ValueError(
                f"chunk_index={c['chunk_index']} exceeds {PER_TEXT_TOKEN_CAP} tokens "
                f"(est {_est_tokens(c['text'])}); refusing to embed"
            )
```

Call at top of `embed_chunks`.

---

## 6. Token-budgeted batch packer (B2.1)

Greedy packer — flush when next chunk would breach token budget OR text count cap:

```python
def _pack_batches(chunks: list[Chunk]) -> Iterator[list[Chunk]]:
    batch: list[Chunk] = []
    batch_tokens = 0
    for c in chunks:
        t = _est_tokens(c["text"])
        would_exceed = (
            batch and (
                batch_tokens + t > EMBED_TOKEN_BUDGET
                or len(batch) >= EMBED_BATCH_HARD_CAP
            )
        )
        if would_exceed:
            yield batch
            batch, batch_tokens = [], 0
        batch.append(c)
        batch_tokens += t
    if batch:
        yield batch
```

---

## 7. Resilient batch call (B2.2 + B3.1)

```python
from google import genai
from google.genai import types, errors
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, errors.ServerError):
        return True  # 5xx
    if isinstance(exc, errors.ClientError):
        return getattr(exc, "code", None) == 429  # rate limit only
    return False

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def _embed_batch_call(
    client: genai.Client,
    texts: list[str],
    task_type: str,
) -> list[list[float]]:
    resp = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIM,
        ),
    )
    return [e.values for e in resp.embeddings]
```

---

## 8. L2-normalization (B2.3 / R1.1)

```python
import numpy as np

def _l2_normalize(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        raise ValueError("zero-norm embedding returned by Gemini")
    return (arr / norm).tolist()
```

---

## 9. `embed_chunks` glue

```python
def embed_chunks(chunks: list[Chunk]) -> list[Embedding]:
    _check_chunk_sizes(chunks)
    client = genai.Client()
    out: list[Embedding] = []
    for batch in _pack_batches(chunks):
        vectors = _embed_batch_call(
            client,
            [c["text"] for c in batch],
            task_type="RETRIEVAL_DOCUMENT",
        )
        for c, v in zip(batch, vectors, strict=True):
            out.append(Embedding(
                chunk_index=c["chunk_index"],
                vector=_l2_normalize(v),
                embedding_model=EMBEDDING_MODEL,
            ))
    return out
```

---

## 10. Persistence

```python
def save_embeddings(embeddings: list[Embedding], path: str | Path) -> None:
    Path(path).write_text(json.dumps(embeddings, ensure_ascii=False))

def load_embeddings(path: str | Path) -> list[Embedding]:
    return json.loads(Path(path).read_text())
```

No `indent=2` — embedding files are large; keep compact. Inspect via `jq` if needed.

---

## 11. `services/eval.py`

Eval case schema (mirrors `temp/eval_cases.json`):

```python
class EvalCase(TypedDict):
    id: str
    query: str
    expected_chunk_indices: list[int]

class CaseResult(TypedDict):
    id: str
    query: str
    hit: bool
    first_hit_rank: int | None  # 1-based; None if no hit in top-k
    top_k_indices: list[int]

class EvalReport(TypedDict):
    k: int
    cases: list[CaseResult]
    mean_recall_at_k: float
    mean_mrr: float
```

Functions:

```python
def embed_query(text: str) -> list[float]:
    client = genai.Client()
    vec = _embed_batch_call(client, [text], task_type="RETRIEVAL_QUERY")[0]
    return _l2_normalize(vec)

def retrieve(
    query_vec: list[float],
    embeddings: list[Embedding],
    k: int = 5,
) -> list[int]:
    q = np.asarray(query_vec, dtype=np.float32)
    mat = np.asarray([e["vector"] for e in embeddings], dtype=np.float32)
    scores = mat @ q  # dot product (vectors L2-normalized → equals cosine)
    top = np.argsort(-scores)[:k]
    return [embeddings[i]["chunk_index"] for i in top]

def recall_at_k(retrieved: list[int], expected: list[int], k: int) -> float:
    if not expected:
        return 0.0
    hits = sum(1 for x in retrieved[:k] if x in expected)
    return hits / len(expected)

def mrr(retrieved: list[int], expected: list[int]) -> float:
    for rank, idx in enumerate(retrieved, start=1):
        if idx in expected:
            return 1.0 / rank
    return 0.0

def run_eval(
    cases: list[EvalCase],
    embeddings: list[Embedding],
    k: int = 5,
) -> EvalReport:
    case_results: list[CaseResult] = []
    for case in cases:
        qv = embed_query(case["query"])
        top = retrieve(qv, embeddings, k=k)
        hit_rank = next(
            (r for r, idx in enumerate(top, start=1) if idx in case["expected_chunk_indices"]),
            None,
        )
        case_results.append(CaseResult(
            id=case["id"],
            query=case["query"],
            hit=hit_rank is not None,
            first_hit_rank=hit_rank,
            top_k_indices=top,
        ))
    mean_r = sum(recall_at_k(r["top_k_indices"], next(c["expected_chunk_indices"] for c in cases if c["id"] == r["id"]), k) for r in case_results) / len(case_results)
    mean_m = sum(mrr(r["top_k_indices"], next(c["expected_chunk_indices"] for c in cases if c["id"] == r["id"])) for r in case_results) / len(case_results)
    return EvalReport(k=k, cases=case_results, mean_recall_at_k=mean_r, mean_mrr=mean_m)

def print_report(report: EvalReport) -> None:
    for r in report["cases"]:
        print(f"[{r['id']}] hit={r['hit']} rank={r['first_hit_rank']} top={r['top_k_indices']} q={r['query']!r}")
    print(f"\nmean Recall@{report['k']}: {report['mean_recall_at_k']:.3f}")
    print(f"mean MRR: {report['mean_mrr']:.3f}")
```

`embed_query` and `_embed_batch_call` are imported from `services.embeddings` to avoid duplicating the retry/normalize logic.

---

## 12. `scripts/probe_gemini_batch.py` (B6.1)

Run once before first full ingestion to validate live API behavior:

```python
"""Probe Gemini embed_content with varying batch sizes."""
import time
from services.embeddings import _embed_batch_call, EMBEDDING_MODEL
from google import genai

SAMPLES = ["sample text " * 50] * 100  # ~300 tokens each, well under per-text cap

def main():
    client = genai.Client()
    for n in (1, 10, 50, 100):
        batch = SAMPLES[:n]
        t0 = time.perf_counter()
        try:
            vecs = _embed_batch_call(client, batch, task_type="RETRIEVAL_DOCUMENT")
            dt = time.perf_counter() - t0
            print(f"batch={n:>3}  ok  vectors={len(vecs)}  dim={len(vecs[0])}  {dt:.2f}s")
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"batch={n:>3}  FAIL  {type(e).__name__}: {e}  {dt:.2f}s")

if __name__ == "__main__":
    main()
```

Success criteria: all four sizes succeed and return `dim=1536`. If batch=100 fails, drop `EMBED_BATCH_HARD_CAP` to the largest passing size.

---

## 13. `scripts/embed_pdf_inspect.py` (B6.2)

End-to-end debug + eval run:

```python
"""Step 3 debug: embed chunks, save, run eval."""
from services.chunker import load_chunks
from services.embeddings import embed_chunks, save_embeddings, load_embeddings
from services.eval import run_eval, print_report
import json

CHUNKS_PATH = "temp/chunks.json"
EMBEDDINGS_PATH = "temp/embeddings.json"
EVAL_CASES_PATH = "temp/eval_cases.json"

def main():
    chunks = load_chunks(CHUNKS_PATH)
    print(f"Loaded {len(chunks)} chunks")

    embeddings = embed_chunks(chunks)
    save_embeddings(embeddings, EMBEDDINGS_PATH)
    print(f"Saved {len(embeddings)} embeddings to {EMBEDDINGS_PATH}")

    # Round-trip sanity check
    reloaded = load_embeddings(EMBEDDINGS_PATH)
    assert len(reloaded) == len(embeddings)

    cases = json.loads(open(EVAL_CASES_PATH).read())
    report = run_eval(cases, reloaded, k=5)
    print_report(report)

if __name__ == "__main__":
    main()
```

---

## 14. `temp/eval_cases.json` (B7) — hand-curate

Format:

```json
[
  {
    "id": "case-01",
    "query": "What is AI engineering?",
    "expected_chunk_indices": [0, 1]
  },
  {
    "id": "case-02",
    "query": "...",
    "expected_chunk_indices": [...]
  }
]
```

Process:

1. Open `temp/chunks.json`, skim to identify ~5–10 distinct topics covered
2. For each: write a natural-language query, note 1–3 `chunk_index` values that should appear in top-5
3. Bias toward queries where the answer is unambiguous to keep ground truth solid

---

## Implementation Order

1. **Deps + `.env`** (steps 1–2) → environment ready
2. **`services/embeddings.py`** (steps 3–10) → core pipeline
3. **`scripts/probe_gemini_batch.py`** (step 12) → run, confirm batch=100 works
4. **Hand-curate `temp/eval_cases.json`** (step 14) → ground truth
5. **`services/eval.py`** (step 11) → retrieval + metrics
6. **`scripts/embed_pdf_inspect.py`** (step 13) → end-to-end
7. Run debug script; eyeball printed eval report

---

## Done When

- `uv sync` installs google-genai, tenacity, python-dotenv, numpy
- `GEMINI_API_KEY` loaded from `.env`; missing key raises clear error before any API call
- Probe script reports `ok` for batch sizes 1, 10, 50, 100 with `dim=1536`
- `services/embeddings.py` exports `Embedding`, `embed_chunks`, `save_embeddings`, `load_embeddings`
- `services/eval.py` exports `EvalCase`, `EvalReport`, `embed_query`, `retrieve`, `recall_at_k`, `mrr`, `run_eval`, `print_report`
- `temp/embeddings.json` contains one entry per chunk in `chunks.json`, each with 1536-dim L2-normalized vector
- `np.linalg.norm(vector)` ≈ 1.0 for every stored vector (within float32 tolerance)
- Pre-flight rejects any chunk estimated > 2,048 tokens (won't fire given Step 2 sizes; defensive)
- Debug script prints per-case `(hit, rank, top_k)` and aggregate `mean Recall@5`, `mean MRR`
- Eval cases (~5–10) are hand-checked and at least the obvious ones hit
- No DB / FastAPI / pgvector / frontend work introduced
