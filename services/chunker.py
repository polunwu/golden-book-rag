import bisect
import json
from pathlib import Path
from typing import TypedDict

import pymupdf

from services.pdf_parser import extract_page_text

CHUNK_SIZE = 500
OVERLAP = 50
STEP = CHUNK_SIZE - OVERLAP


class Chunk(TypedDict):
    text: str
    page_start: int
    page_end: int
    section_path: list[str]
    section_title: str | None
    section_level: int | None
    chunk_index: int


def _build_page_offsets(
    doc: pymupdf.Document,
) -> tuple[str, list[tuple[int, int, int]]]:
    full_text = ""
    offsets: list[tuple[int, int, int]] = []
    for pdf_page in range(1, doc.page_count + 1):
        page_text = extract_page_text(doc, pdf_page)
        start = len(full_text)
        full_text += page_text
        offsets.append((start, len(full_text), pdf_page))
    return full_text, offsets


def _char_to_page(offsets: list[tuple[int, int, int]], pos: int) -> int:
    starts = [s for s, _, _ in offsets]
    idx = max(0, bisect.bisect_right(starts, pos) - 1)
    return offsets[idx][2]


def _build_toc_section_lookup(toc: list[tuple[int, str, int]]):
    snapshots: list[tuple[int, dict[int, str]]] = []
    active: dict[int, str] = {}
    for level, title, pdf_page in toc:
        for k in [k for k in active if k >= level]:
            del active[k]
        active[level] = title
        snapshots.append((pdf_page, dict(active)))

    def lookup(page: int) -> tuple[list[str], str | None, int | None]:
        if not snapshots:
            return [], None, None
        idx = bisect.bisect_right([p for p, _ in snapshots], page) - 1
        if idx < 0:
            return [], None, None
        active_snap = snapshots[idx][1]
        if not active_snap:
            return [], None, None
        path = [active_snap[l] for l in sorted(active_snap)]
        max_level = max(active_snap)
        return path, active_snap[max_level], max_level

    return lookup


def chunk_pdf(doc: pymupdf.Document) -> list[Chunk]:
    full_text, offsets = _build_page_offsets(doc)
    lookup_section = _build_toc_section_lookup(doc.get_toc())

    chunks: list[Chunk] = []
    i = 0
    chunk_index = 0
    while i < len(full_text):
        text = full_text[i : i + CHUNK_SIZE]
        page_start = _char_to_page(offsets, i)
        page_end = _char_to_page(offsets, min(i + CHUNK_SIZE - 1, len(full_text) - 1))
        section_path, section_title, section_level = lookup_section(page_start)
        chunks.append(
            Chunk(
                text=text,
                page_start=page_start,
                page_end=page_end,
                section_path=section_path,
                section_title=section_title,
                section_level=section_level,
                chunk_index=chunk_index,
            )
        )
        chunk_index += 1
        i += STEP

    return chunks


def save_chunks(chunks: list[Chunk], path: str | Path) -> None:
    Path(path).write_text(json.dumps(chunks, ensure_ascii=False, indent=2))


def load_chunks(path: str | Path) -> list[Chunk]:
    return json.loads(Path(path).read_text())
