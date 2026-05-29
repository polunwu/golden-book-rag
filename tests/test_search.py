"""POST /books/{id}/search — gating + ranked retrieval.

Gemini is stubbed (conftest._no_gemini): _fake_embed_query == chunk_index 0's
stored vector, so chunk_index 0 is the deterministic top hit.
"""
from __future__ import annotations

import uuid

from tests._helpers import make_pdf_bytes, upload


def _ready_book(client, book_ids, *, title="searchable") -> uuid.UUID:
    resp = upload(client, book_ids, content=make_pdf_bytes(title), title=title)
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "ready"
    return bid


# --- gating -------------------------------------------------------------

def test_search_unknown_book_404(client):
    resp = client.post(f"/books/{uuid.uuid4()}/search", json={"query": "x"})
    assert resp.status_code == 404


def test_search_not_ready_409(client, book_ids):
    # zero-byte PDF → background ingest lands at 'failed' (non-ready)
    resp = upload(client, book_ids, content=b"", title="broken")
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "failed"

    resp = client.post(f"/books/{bid}/search", json={"query": "x"})
    assert resp.status_code == 409
    assert "status=failed" in resp.json()["detail"]


def test_search_empty_query_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/search", json={"query": ""}).status_code == 422
    assert client.post(f"/books/{bid}/search", json={"query": "   "}).status_code == 422


def test_search_k_out_of_range_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/search", json={"query": "x", "k": 0}).status_code == 422
    assert client.post(f"/books/{bid}/search", json={"query": "x", "k": 21}).status_code == 422


# --- happy path ---------------------------------------------------------

def test_search_happy_path_ranked(client, book_ids):
    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/search", json={"query": "anything", "k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == str(bid)
    assert body["k"] == 5
    hits = body["hits"]
    assert 1 <= len(hits) <= 5
    # deterministic stub → chunk_index 0 is the nearest
    assert hits[0]["chunk_index"] == 0
    # scores are descending and carry citation metadata
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert "text" in hits[0] and "page_start" in hits[0]


# --- scoping ------------------------------------------------------------

def test_search_scoped_to_book(client, book_ids):
    a = _ready_book(client, book_ids, title="book A")
    _ready_book(client, book_ids, title="book B")  # noise — must not leak in

    a_total = client.get(f"/books/{a}/chunks").json()["total"]
    # k=20 (the max) ≫ these single-page books' chunk counts, so a correctly
    # scoped search returns exactly book A's chunks, never book B's.
    assert a_total <= 20
    resp = client.post(f"/books/{a}/search", json={"query": "x", "k": 20})
    assert resp.status_code == 200
    assert len(resp.json()["hits"]) == a_total
