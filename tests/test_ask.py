"""POST /books/{id}/ask — gating, grounded answer, refusal floor.

Gemini is stubbed (conftest._no_gemini): _fake_embed_query == chunk_index 0's
stored vector (top hit, distance ~0 -> score ~1.0), and generate_answer returns
a GroundedAnswer(can_answer=True, ...). Hard refusal is forced by raising
ASK_SCORE_FLOOR above 1.0; soft refusal by stubbing generate_answer to
can_answer=False.
"""
from __future__ import annotations

import uuid
from unittest.mock import Mock

from tests._helpers import make_pdf_bytes, upload


def _ready_book(client, book_ids, *, title="askable") -> uuid.UUID:
    resp = upload(client, book_ids, content=make_pdf_bytes(title), title=title)
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "ready"
    return bid


# --- gating -------------------------------------------------------------

def test_ask_unknown_book_404(client):
    resp = client.post(f"/books/{uuid.uuid4()}/ask", json={"query": "x"})
    assert resp.status_code == 404


def test_ask_not_ready_409(client, book_ids):
    resp = upload(client, book_ids, content=b"", title="broken")  # zero-byte -> failed
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "failed"
    resp = client.post(f"/books/{bid}/ask", json={"query": "x"})
    assert resp.status_code == 409
    assert "status=failed" in resp.json()["detail"]


def test_ask_empty_query_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/ask", json={"query": ""}).status_code == 422
    assert client.post(f"/books/{bid}/ask", json={"query": "   "}).status_code == 422


def test_ask_k_out_of_range_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/ask", json={"query": "x", "k": 0}).status_code == 422
    assert client.post(f"/books/{bid}/ask", json={"query": "x", "k": 21}).status_code == 422


# --- grounded happy path ------------------------------------------------

def test_ask_grounded_200(client, book_ids):
    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/ask", json={"query": "anything", "k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == str(bid)
    assert body["refused"] is False
    assert body["answer"]  # non-empty (stubbed)
    cites = body["citations"]
    assert 1 <= len(cites) <= 5
    # markers are 1..N in order; scores descending; citation metadata present
    assert [c["marker"] for c in cites] == list(range(1, len(cites) + 1))
    assert cites[0]["score"] == max(c["score"] for c in cites)
    assert "text" in cites[0] and "page_start" in cites[0]


# --- refusal floor ------------------------------------------------------

def test_ask_refusal_floor_no_generation(client, book_ids, monkeypatch):
    """Floor above 1.0 forces refusal; generation must NOT be called."""
    import services.generate as generate_mod
    spy = Mock(side_effect=AssertionError("generate_answer must not be called"))
    monkeypatch.setattr(generate_mod, "generate_answer", spy)
    monkeypatch.setenv("ASK_SCORE_FLOOR", "1.5")

    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/ask", json={"query": "anything"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert body["answer"]  # language-matched refusal string
    spy.assert_not_called()


def test_ask_soft_refusal_language_matched(client, book_ids, monkeypatch):
    """Retrieval clears the floor but the model judges the excerpts insufficient
    (can_answer=False): same contract as the hard refusal — refused=True, no
    citations, message in the query's language (here Chinese), NOT the model's
    own (English) prose."""
    import services.generate as generate_mod
    from services.generate import GroundedAnswer
    monkeypatch.setattr(
        generate_mod, "generate_answer",
        lambda query, hits: GroundedAnswer(can_answer=False, answer=""),
    )
    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/ask", json={"query": "如何煮義大利麵？", "k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert any("一" <= ch <= "鿿" for ch in body["answer"])
