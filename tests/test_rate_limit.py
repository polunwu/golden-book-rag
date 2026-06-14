"""Guest daily cap (V2): global pools for ask + search, 429 before any Gemini
call, admin uncapped, anonymous cookie minted.

Gemini is stubbed (conftest._no_gemini); the counters live in `ask_usage`, reset
before each test by the autouse `_reset_usage` fixture. Limits are read at call
time, so `monkeypatch.setenv` sets a low cap per test.
"""
from __future__ import annotations

import uuid
from unittest.mock import Mock

import pytest

from db.connection import get_pool
from tests._helpers import ADMIN_HEADERS, make_pdf_bytes, upload


def _ready_book(client, book_ids, *, title="askable") -> uuid.UUID:
    resp = upload(client, book_ids, content=make_pdf_bytes(title), title=title)
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "ready"
    return bid


def _usage() -> dict[str, int]:
    """Current ask_usage counts keyed by bucket (one test == one UTC day)."""
    with get_pool().connection() as conn:
        rows = conn.execute("SELECT bucket, count FROM ask_usage").fetchall()
    return {r["bucket"]: r["count"] for r in rows}


# --- guest cap enforced, no Gemini past the limit ------------------------

def test_guest_ask_capped_no_gemini_past_limit(client, book_ids, monkeypatch):
    monkeypatch.setenv("ASK_DAILY_LIMIT", "2")
    bid = _ready_book(client, book_ids)

    import api.routers.books as books_mod
    spy = Mock(side_effect=books_mod.embed_query)  # wrap the conftest stub
    monkeypatch.setattr(books_mod, "embed_query", spy)

    for _ in range(2):
        assert client.post(f"/books/{bid}/ask", json={"query": "x"}).status_code == 200

    resp = client.post(f"/books/{bid}/ask", json={"query": "x"})
    assert resp.status_code == 429
    assert "daily limit" in resp.json()["detail"]
    assert resp.headers["x-ratelimit-remaining"] == "0"
    # The blocked request never reached embed_query (quota precedes Gemini).
    assert spy.call_count == 2


def test_guest_ask_no_retrieve_capped(client, book_ids, monkeypatch):
    """retrieve=false still spends Gemini (generate_plain_answer), so it's gated
    too — and the plain path is not called once over the cap."""
    monkeypatch.setenv("ASK_DAILY_LIMIT", "1")
    bid = _ready_book(client, book_ids)

    import api.routers.books as books_mod
    spy = Mock(side_effect=books_mod.generate_plain_answer)
    monkeypatch.setattr(books_mod, "generate_plain_answer", spy)

    assert client.post(
        f"/books/{bid}/ask?retrieve=false", json={"query": "x"}
    ).status_code == 200
    assert client.post(
        f"/books/{bid}/ask?retrieve=false", json={"query": "x"}
    ).status_code == 429
    assert spy.call_count == 1


# --- admin is never capped (R5) ------------------------------------------

def test_admin_ask_uncapped(client, book_ids, monkeypatch):
    monkeypatch.setenv("ASK_DAILY_LIMIT", "1")
    bid = _ready_book(client, book_ids)
    for _ in range(3):
        resp = client.post(
            f"/books/{bid}/ask", json={"query": "x"}, headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200
    # No counting happened for the admin.
    assert _usage() == {}


# --- ask and search are independent pools --------------------------------

def test_ask_and_search_separate_pools(client, book_ids, monkeypatch):
    monkeypatch.setenv("ASK_DAILY_LIMIT", "1")
    monkeypatch.setenv("SEARCH_DAILY_LIMIT", "1")
    bid = _ready_book(client, book_ids)

    assert client.post(f"/books/{bid}/ask", json={"query": "x"}).status_code == 200
    assert client.post(f"/books/{bid}/ask", json={"query": "x"}).status_code == 429
    # Search has its own pool — exhausting ask doesn't touch it.
    assert client.post(f"/books/{bid}/search", json={"query": "x"}).status_code == 200
    assert client.post(f"/books/{bid}/search", json={"query": "x"}).status_code == 429


# --- anonymous cookie minted + reused ------------------------------------

def test_guest_cookie_minted_and_reused(client, book_ids):
    bid = _ready_book(client, book_ids)
    client.cookies.clear()

    first = client.post(f"/books/{bid}/ask", json={"query": "x"})
    assert first.status_code == 200
    assert "bookrag_gid" in first.headers.get("set-cookie", "")
    gid = client.cookies.get("bookrag_gid")
    assert gid

    # Cookie now present → no fresh mint on the next request.
    second = client.post(f"/books/{bid}/ask", json={"query": "x"})
    assert "set-cookie" not in second.headers
    assert client.cookies.get("bookrag_gid") == gid


# --- only the enforced global bucket is counted --------------------------

def test_only_global_bucket_counted(client, book_ids):
    bid = _ready_book(client, book_ids)
    for _ in range(2):
        assert client.post(f"/books/{bid}/ask", json={"query": "x"}).status_code == 200

    usage = _usage()
    assert usage == {"global:ask": 2}  # no per-guest rows
