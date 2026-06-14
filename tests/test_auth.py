"""Admin write-gate on upload/delete; read/search/ask stay open (V1).

`ADMIN_SECRET` is set by conftest's autouse `_admin_secret` fixture; tests that
need a missing/wrong credential override it via the `client`/`monkeypatch` env.
Gemini stays stubbed (conftest._no_gemini).
"""
from __future__ import annotations

import io
import uuid

import pytest

from tests._helpers import (
    ADMIN_HEADERS,
    ADMIN_SECRET,
    make_pdf_bytes,
    pdf_part,
    upload,
)


def _upload_raw(client, *, headers=None):
    """POST upload directly (bypassing the helper's auto-header) so the gate's
    missing/wrong-credential branches can be exercised."""
    return client.post(
        "/books/upload",
        files=pdf_part(make_pdf_bytes()),
        data={"title": "gated"},
        headers=headers or {},
    )


# --- write gate: upload -------------------------------------------------

def test_upload_no_header_401(client):
    resp = _upload_raw(client)
    assert resp.status_code == 401


def test_upload_wrong_secret_403(client):
    resp = _upload_raw(client, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 403


def test_upload_non_ascii_token_403_not_500(client):
    # Send a raw latin-1 byte (0xe9); Starlette decodes the header as latin-1, so
    # the gate sees a non-ASCII str and must reject it cleanly, not raise
    # TypeError inside hmac.compare_digest.
    resp = _upload_raw(client, headers={"Authorization": b"Bearer \xe9"})
    assert resp.status_code == 403


def test_upload_correct_secret_202(client, book_ids):
    # The helper attaches ADMIN_HEADERS and tracks the id for teardown.
    resp = upload(client, book_ids, content=make_pdf_bytes("ok"), title="ok")
    assert resp.status_code == 202


# --- write gate: delete -------------------------------------------------

def test_delete_no_header_401(client, book_ids):
    resp = upload(client, book_ids, content=make_pdf_bytes(), title="del")
    bid = book_ids[-1]
    assert client.delete(f"/books/{bid}").status_code == 401


def test_delete_wrong_secret_403(client, book_ids):
    resp = upload(client, book_ids, content=make_pdf_bytes(), title="del")
    bid = book_ids[-1]
    resp = client.delete(
        f"/books/{bid}", headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 403


def test_delete_correct_secret_204(client, book_ids):
    resp = upload(client, book_ids, content=make_pdf_bytes(), title="del")
    bid = book_ids[-1]
    assert client.delete(f"/books/{bid}", headers=ADMIN_HEADERS).status_code == 204


# --- reads/search/ask stay open ----------------------------------------

def test_reads_open_without_header(client, book_ids):
    # Seed via the (gated) helper, then read back with no credential.
    resp = upload(client, book_ids, content=make_pdf_bytes("open"), title="open")
    bid = book_ids[-1]
    assert client.get("/books").status_code == 200
    assert client.get(f"/books/{bid}").status_code == 200
    assert client.get(f"/books/{bid}/chunks").status_code == 200
    # search + ask need a ready book — the stub ingest lands at 'ready'.
    assert client.get(f"/books/{bid}").json()["status"] == "ready"
    assert client.post(f"/books/{bid}/search", json={"query": "x"}).status_code == 200
    assert client.post(f"/books/{bid}/ask", json={"query": "x"}).status_code == 200


# --- unconfigured deploy: nobody is admin -------------------------------

def test_unset_secret_blocks_all_writes(client, monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    # Even the "correct" secret can't match an unset env → missing is still 401,
    # and presenting any token is 403 (no admin possible).
    assert _upload_raw(client).status_code == 401
    resp = _upload_raw(client, headers=ADMIN_HEADERS)
    assert resp.status_code == 403
