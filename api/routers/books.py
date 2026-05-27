from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import DictRow

from api.deps import get_conn
from api.schemas import BookList, BookOut, ChunkOut, ChunkPage

router = APIRouter(prefix="/books", tags=["books"])

_BOOK_COLS = "id, title, file_path, created_at, status, error_message"
_CHUNK_COLS = (
    "chunk_index, text, page_start, page_end, "
    "section_path, section_title, section_level"
)


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
