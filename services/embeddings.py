import json
import os
from pathlib import Path
from typing import Iterator, TypedDict

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from services.chunker import Chunk

load_dotenv()

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 1536
EMBED_TOKEN_BUDGET = 18_000
EMBED_BATCH_HARD_CAP = 100
PER_TEXT_TOKEN_CAP = 2_048
TOKENS_PER_LATIN_CHAR = 0.25
TOKENS_PER_CJK_CHAR = 1.0

_CJK_RANGES = (
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0xFF00, 0xFFEF),  # Halfwidth / Fullwidth forms
)


class Embedding(TypedDict):
    chunk_index: int
    vector: list[float]
    embedding_model: str


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def _est_tokens(text: str) -> int:
    cjk = sum(1 for c in text if _is_cjk(c))
    latin = len(text) - cjk
    return max(1, int(cjk * TOKENS_PER_CJK_CHAR + latin * TOKENS_PER_LATIN_CHAR))


def make_client() -> genai.Client:
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY missing — set in .env or environment")
    return genai.Client()


def _check_chunk_sizes(chunks: list[Chunk]) -> None:
    for c in chunks:
        est = _est_tokens(c["text"])
        if est > PER_TEXT_TOKEN_CAP:
            raise ValueError(
                f"chunk_index={c['chunk_index']} exceeds {PER_TEXT_TOKEN_CAP} tokens "
                f"(est {est}); refusing to embed"
            )


def _pack_batches(chunks: list[Chunk]) -> Iterator[list[Chunk]]:
    batch: list[Chunk] = []
    batch_tokens = 0
    for c in chunks:
        t = _est_tokens(c["text"])
        would_exceed = batch and (
            batch_tokens + t > EMBED_TOKEN_BUDGET
            or len(batch) >= EMBED_BATCH_HARD_CAP
        )
        if would_exceed:
            yield batch
            batch, batch_tokens = [], 0
        batch.append(c)
        batch_tokens += t
    if batch:
        yield batch


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, errors.ServerError):
        return True
    if isinstance(exc, errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def embed_batch_call(
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
    if resp.embeddings is None:
        raise RuntimeError("Gemini returned no embeddings")
    out: list[list[float]] = []
    for i, e in enumerate(resp.embeddings):
        if e.values is None:
            raise RuntimeError(f"Gemini returned null vector at index {i}")
        out.append(e.values)
    return out


def l2_normalize(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        raise ValueError("zero-norm embedding returned by Gemini")
    return (arr / norm).tolist()


def embed_query(text: str) -> list[float]:
    """Embed a search query. RETRIEVAL_QUERY task type (asymmetric vs the
    RETRIEVAL_DOCUMENT chunks); L2-normalized so cosine distance == 1 - dot."""
    client = make_client()
    vec = embed_batch_call(client, [text], task_type="RETRIEVAL_QUERY")[0]
    return l2_normalize(vec)


def embed_chunks(chunks: list[Chunk]) -> list[Embedding]:
    _check_chunk_sizes(chunks)
    client = make_client()
    out: list[Embedding] = []
    for batch in _pack_batches(chunks):
        vectors = embed_batch_call(
            client,
            [c["text"] for c in batch],
            task_type="RETRIEVAL_DOCUMENT",
        )
        for c, v in zip(batch, vectors, strict=True):
            out.append(
                Embedding(
                    chunk_index=c["chunk_index"],
                    vector=l2_normalize(v),
                    embedding_model=EMBEDDING_MODEL,
                )
            )
    return out


def save_embeddings(embeddings: list[Embedding], path: str | Path) -> None:
    Path(path).write_text(json.dumps(embeddings, ensure_ascii=False))


def load_embeddings(path: str | Path) -> list[Embedding]:
    return json.loads(Path(path).read_text())
