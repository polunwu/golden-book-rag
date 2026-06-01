import os
import uuid
from pathlib import Path
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, Query,
    Response,
)
from psycopg.rows import DictRow

from api.deps import get_conn
from api.schemas import (
    AskRequest, AskResponse, BookList, BookOut, ChunkOut, ChunkPage, Citation,
    SearchHit, SearchRequest, SearchResponse, UploadBookForm, UploadResponse,
)
from services.embeddings import embed_query
from services.generate import generate_answer, refusal_text, should_refuse
from services.ingest import run_ingest
from services.retrieval import search_chunks

router = APIRouter(prefix="/books", tags=["books"])

_BOOK_COLS = "id, title, file_path, created_at, status, error_message"
_CHUNK_COLS = (
    "chunk_index, text, page_start, page_end, "
    "section_path, section_title, section_level"
)


def _max_upload_bytes() -> int:
    return int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024


def _upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "uploads"))


def _score_floor() -> float:
    return float(os.environ.get("ASK_SCORE_FLOOR", "0.6"))


@router.post("/upload", response_model=UploadResponse, status_code=202)
def upload_book(
    background_tasks: BackgroundTasks,
    form: Annotated[UploadBookForm, File()],
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> UploadResponse:
    file, title, book_id = form.file, form.title, form.book_id
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="file must be application/pdf")
    if not title.strip():
        raise HTTPException(status_code=422, detail="title must not be empty")

    if book_id is not None:
        try:
            resolved_id = uuid.UUID(book_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="book_id must be a UUID")
        exists = conn.execute(
            "SELECT 1 FROM books WHERE id = %s", (resolved_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(
                status_code=404, detail="unknown book_id; omit to create new",
            )
    else:
        resolved_id = uuid.uuid4()

    # Stream to .partial, then atomic rename — keeps any existing pdf_path
    # intact until size validation passes (re-ingest safety).
    pdf_path = _upload_dir() / f"{resolved_id}.pdf"
    tmp_path = pdf_path.with_name(f"{resolved_id}.pdf.partial")
    max_bytes = _max_upload_bytes()
    written = 0
    try:
        with tmp_path.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"file exceeds MAX_UPLOAD_MB={max_bytes // (1024 * 1024)}",
                    )
                out.write(chunk)
        os.replace(tmp_path, pdf_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO books (id, title, file_path, status, error_message) "
            "VALUES (%s, %s, %s, 'pending', NULL) "
            "ON CONFLICT (id) DO UPDATE SET "
            "title = EXCLUDED.title, file_path = EXCLUDED.file_path, "
            "status = 'pending', error_message = NULL",
            (resolved_id, title, str(pdf_path)),
        )
    conn.commit()

    background_tasks.add_task(run_ingest, resolved_id, str(pdf_path), title)
    return UploadResponse(book_id=resolved_id, status="pending")


@router.get("", response_model=BookList)
def list_books(conn: psycopg.Connection[DictRow] = Depends(get_conn)) -> BookList:
    rows = conn.execute(
        f"SELECT {_BOOK_COLS} FROM books ORDER BY created_at DESC"
    ).fetchall()
    return BookList(items=[BookOut.model_validate(r) for r in rows])


@router.get("/{book_id}", response_model=BookOut)
def get_book(
    book_id: UUID,
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> BookOut:
    row = conn.execute(
        f"SELECT {_BOOK_COLS} FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")
    return BookOut.model_validate(row)


@router.get("/{book_id}/chunks", response_model=ChunkPage)
def get_chunks(
    book_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> ChunkPage:
    exists = conn.execute(
        "SELECT 1 FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="book not found")

    total_row = conn.execute(
        "SELECT count(*) AS total FROM chunks WHERE book_id = %s", (book_id,)
    ).fetchone()
    assert total_row is not None
    total = total_row["total"]

    rows = conn.execute(
        f"SELECT {_CHUNK_COLS} FROM chunks WHERE book_id = %s "
        f"ORDER BY chunk_index LIMIT %s OFFSET %s",
        (book_id, limit, offset),
    ).fetchall()
    return ChunkPage(
        items=[ChunkOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post("/{book_id}/search", response_model=SearchResponse)
def search_book(
    book_id: UUID,
    body: SearchRequest,
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> SearchResponse:
    row = conn.execute(
        "SELECT status FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")
    if row["status"] != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"book not ready for search (status={row['status']})",
        )

    query_vec = embed_query(body.query)
    hits = search_chunks(conn, book_id, query_vec, body.k)
    return SearchResponse(
        book_id=book_id,
        query=body.query,
        k=body.k,
        hits=[
            # h shares ChunkBase with SearchHit; drop distance, derive score.
            SearchHit(**h.model_dump(exclude={"distance"}), score=1.0 - h.distance)
            for h in hits
        ],
    )


@router.post("/{book_id}/ask", response_model=AskResponse)
def ask_book(
    book_id: UUID,
    body: AskRequest,
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> AskResponse:
    row = conn.execute(
        "SELECT status FROM books WHERE id = %s", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")
    if row["status"] != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"book not ready for ask (status={row['status']})",
        )

    query_vec = embed_query(body.query)
    hits = search_chunks(conn, book_id, query_vec, body.k)

    if should_refuse(hits, _score_floor()):
        return AskResponse(
            book_id=book_id, query=body.query, k=body.k,
            answer=refusal_text(body.query), refused=True, citations=[],
        )

    answer = generate_answer(body.query, hits)
    citations = [
        # h shares ChunkBase with Citation; drop distance, add marker + score.
        Citation(**h.model_dump(exclude={"distance"}), marker=i, score=1.0 - h.distance)
        for i, h in enumerate(hits, start=1)
    ]
    return AskResponse(
        book_id=book_id, query=body.query, k=body.k,
        answer=answer, refused=False, citations=citations,
    )


@router.delete("/{book_id}", status_code=204)
def delete_book(
    book_id: UUID,
    conn: psycopg.Connection[DictRow] = Depends(get_conn),
) -> Response:
    row = conn.execute(
        "DELETE FROM books WHERE id = %s RETURNING file_path", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")
    conn.commit()
    if row["file_path"]:
        Path(row["file_path"]).unlink(missing_ok=True)
    return Response(status_code=204)
