from pydantic import BaseModel


class ChunkBase(BaseModel):
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: list[str] | None
    section_title: str | None
    section_level: int | None
