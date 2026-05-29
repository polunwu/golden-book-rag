from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator

from services.types import ChunkBase

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


class ChunkOut(ChunkBase):
    pass


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


class UploadBookForm(BaseModel):
    file: UploadFile
    title: str
    book_id: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v


class SearchHit(ChunkBase):
    score: float


class SearchResponse(BaseModel):
    book_id: UUID
    query: str
    k: int
    hits: list[SearchHit]
