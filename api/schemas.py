from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

BookStatus = Literal["pending", "processing", "ready", "failed"]


class BookOut(BaseModel):
    id: UUID
    title: str | None
    file_path: str | None
    created_at: datetime
    status: BookStatus
    error_message: str | None = None


class BookList(BaseModel):
    items: list[BookOut]


class ChunkOut(BaseModel):
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: list[str] | None
    section_title: str | None
    section_level: int | None


class ChunkPage(BaseModel):
    items: list[ChunkOut]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    detail: str


class UploadResponse(BaseModel):
    book_id: UUID
    status: BookStatus
