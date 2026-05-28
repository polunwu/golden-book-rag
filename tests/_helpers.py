"""Pure test helpers — no fixtures. Imported by test modules.

Lives outside conftest.py because conftest is pytest's plugin-discovery
entry point, not an application module to import from.
"""
from __future__ import annotations

import io
import uuid
from typing import BinaryIO

import httpx
import pymupdf
from fastapi.testclient import TestClient


def make_pdf_bytes(text: str = "Hello test page") -> bytes:
    doc = pymupdf.Document()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def pdf_part(
    content: bytes, filename: str = "t.pdf"
) -> dict[str, tuple[str, BinaryIO, str]]:
    return {"file": (filename, io.BytesIO(content), "application/pdf")}


def upload(
    client: TestClient,
    book_ids: list[uuid.UUID],
    *,
    content: bytes,
    title: str,
    book_id: uuid.UUID | None = None,
) -> httpx.Response:
    """POST /books/upload + track created id atomically. Closes the leak
    window between '202 received' and 'book_ids.append' — if the call
    succeeded the id is tracked even if a downstream assert later fails."""
    data: dict[str, str] = {"title": title}
    if book_id is not None:
        data["book_id"] = str(book_id)
    resp = client.post("/books/upload", files=pdf_part(content), data=data)
    if resp.status_code == 202:
        book_ids.append(uuid.UUID(resp.json()["book_id"]))
    return resp
