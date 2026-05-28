"""POST /books/upload + background ingest lifecycle.

FastAPI TestClient runs BackgroundTasks synchronously before .post() returns,
so we can assert the final `ready`/`failed` state in the same request cycle.
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from tests._helpers import make_pdf_bytes, pdf_part, upload


# --- validation (no DB writes expected) ---------------------------------

def test_rejects_non_pdf_content_type(client):
    resp = client.post(
        "/books/upload",
        files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
        data={"title": "t"},
    )
    assert resp.status_code == 422
    assert "application/pdf" in resp.json()["detail"]


def test_rejects_empty_title(client):
    resp = client.post(
        "/books/upload",
        files=pdf_part(make_pdf_bytes()),
        data={"title": "   "},
    )
    assert resp.status_code == 422


def test_rejects_malformed_book_id(client):
    resp = client.post(
        "/books/upload",
        files=pdf_part(make_pdf_bytes()),
        data={"title": "t", "book_id": "not-a-uuid"},
    )
    assert resp.status_code == 422


def test_rejects_unknown_book_id(client):
    resp = client.post(
        "/books/upload",
        files=pdf_part(make_pdf_bytes()),
        data={"title": "t", "book_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# --- happy path (uses fake embeddings) ---------------------------------

def test_upload_happy_path_reaches_ready(client, book_ids, upload_dir):
    resp = upload(client, book_ids,
                  content=make_pdf_bytes("happy path body"), title="happy")
    assert resp.status_code == 202
    bid = book_ids[-1]

    # BackgroundTasks ran inline → status should already be terminal
    detail = client.get(f"/books/{bid}").json()
    assert detail["status"] == "ready"
    assert detail["error_message"] is None
    assert Path(detail["file_path"]).exists()

    chunks = client.get(f"/books/{bid}/chunks").json()
    assert chunks["total"] >= 1


# --- failure path: PDF won't open → bg task lands at failed ------------

def test_zero_byte_pdf_lands_at_failed(client, book_ids):
    resp = upload(client, book_ids, content=b"", title="broken")
    assert resp.status_code == 202
    bid = book_ids[-1]

    detail = client.get(f"/books/{bid}").json()
    assert detail["status"] == "failed"
    assert detail["error_message"]


# --- B1 regression: oversize re-upload must NOT touch existing file ----

def test_oversize_reupload_preserves_existing_pdf(
    client, book_ids, monkeypatch
):
    # 1) seed a ready book
    seed = upload(client, book_ids,
                  content=make_pdf_bytes("original content"), title="keep me")
    assert seed.status_code == 202
    bid = book_ids[-1]

    before = client.get(f"/books/{bid}").json()
    assert before["status"] == "ready"
    pdf_path = Path(before["file_path"])
    original_bytes = pdf_path.read_bytes()
    assert len(original_bytes) > 0

    # 2) re-upload SAME book_id with a size cap that any non-empty body breaks
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    resp = upload(client, book_ids,
                  content=make_pdf_bytes("oversized replacement"),
                  title="should not stick", book_id=bid)
    assert resp.status_code == 413

    # 3) existing file + DB row must be untouched
    assert pdf_path.read_bytes() == original_bytes
    after = client.get(f"/books/{bid}").json()
    assert after["status"] == "ready"
    assert after["title"] == "keep me"

    # 4) no .partial leftover
    assert not pdf_path.with_name(f"{bid}.pdf.partial").exists()
