"""Test fixtures for FastAPI upload + background ingest.

Assumes:
  - docker compose db is up (DATABASE_URL points at it)
  - alembic migrations applied (`make db-migrate`)

Gemini is NEVER called: the autouse `_no_gemini` fixture monkeypatches
`services.ingest.embed_chunks` with a deterministic stub that returns
1536-dim L2-normalised vectors derived from chunk_index.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import numpy as np
import pytest
from fastapi.testclient import TestClient

from db.connection import get_pool
from services.chunker import Chunk
from services.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL, Embedding


def _fake_embed_chunks(chunks: list[Chunk]) -> list[Embedding]:
    out: list[Embedding] = []
    for c in chunks:
        rng = np.random.default_rng(c["chunk_index"])
        v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        v /= np.linalg.norm(v)
        out.append(Embedding(
            chunk_index=c["chunk_index"],
            vector=v.tolist(),
            embedding_model=EMBEDDING_MODEL,
        ))
    return out


def _fake_embed_query(text: str) -> list[float]:
    # Matches _fake_embed_chunks' rng(chunk_index=0) → top hit is chunk_index 0.
    rng = np.random.default_rng(0)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


def _fake_generate_answer(query: str, hits: list) -> str:
    # Deterministic, no network. Emits an inline marker so citation wiring is
    # exercised; mirrors the query language loosely (test asserts structure,
    # not phrasing).
    return f"Stub answer for {query!r}, grounded in the excerpts [1]."


@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.routers.books as books_mod
    import services.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "embed_chunks", _fake_embed_chunks)
    monkeypatch.setattr(books_mod, "embed_query", _fake_embed_query)
    monkeypatch.setattr(books_mod, "generate_answer", _fake_generate_answer)


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """Single TestClient for the session — lifespan opens the pool once.
    `_upload_dir()` / `_max_upload_bytes()` re-read env at request time, so
    per-test env overrides still take effect."""
    from api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolate per-test uploads to tmp_path. Clears MAX_UPLOAD_MB so the
    handler's own default (100) applies — tests that need a different cap
    set it explicitly."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(d))
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    return d


@pytest.fixture
def book_ids() -> Iterator[list[uuid.UUID]]:
    """Track ids created during the test; DELETE CASCADE on teardown."""
    created: list[uuid.UUID] = []
    yield created
    if not created:
        return
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM books WHERE id = ANY(%s)", (created,))
        conn.commit()
