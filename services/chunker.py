import bisect
import json
import re
from pathlib import Path
from typing import Callable, TypedDict

import pymupdf

CHUNK_SIZE = 1024

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_HYPHEN_LINE_BREAK = re.compile(r"[-‐-―]\n(\w)")
_WHITESPACE = re.compile(r"\s+")
_NOISE_CHARS = set(". ")
_NOISE_RATIO = 0.5


def _normalize(text: str) -> str:
    text = _HYPHEN_LINE_BREAK.sub(r"\1", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


def _is_noise(text: str) -> bool:
    if not text:
        return True
    noise = sum(1 for c in text if c in _NOISE_CHARS)
    return noise / len(text) > _NOISE_RATIO


class Chunk(TypedDict):
    text: str
    page_start: int
    page_end: int
    section_path: list[str]
    section_title: str | None
    section_level: int | None
    chunk_index: int


def _extract_blocks(doc: pymupdf.Document) -> list[tuple[str, int]]:
    blocks: list[tuple[str, int]] = []
    for pdf_page in range(1, doc.page_count + 1):
        raw = doc[pdf_page - 1].get_text("blocks")
        for b in raw:
            block_type = b[6]
            if block_type != 0:
                continue
            text = _normalize(b[4])
            if not text or _is_noise(text):
                continue
            blocks.append((text, pdf_page))
    return blocks


def _split_oversized(blocks: list[tuple[str, int]]) -> list[tuple[str, int]]:
    fragments: list[tuple[str, int]] = []
    for text, page in blocks:
        if len(text) <= CHUNK_SIZE:
            fragments.append((text, page))
            continue
        for sentence in _SENTENCE_SPLIT.split(text):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= CHUNK_SIZE:
                fragments.append((sentence, page))
            else:
                for i in range(0, len(sentence), CHUNK_SIZE):
                    fragments.append((sentence[i : i + CHUNK_SIZE], page))
    return fragments


def _build_toc_section_lookup(
    toc: list[tuple[int, str, int]],
) -> Callable[[int], tuple[list[str], str | None, int | None]]:
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


def _pack_chunks(
    fragments: list[tuple[str, int]],
    lookup_section: Callable[[int], tuple[list[str], str | None, int | None]],
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[tuple[str, int]] = []
    buffer_len = 0
    chunk_index = 0

    def emit() -> None:
        nonlocal chunk_index
        text = " ".join(f for f, _ in buffer)
        page_start = buffer[0][1]
        page_end = buffer[-1][1]
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

    for frag_text, page in fragments:
        addition = len(frag_text) + (1 if buffer else 0)
        if buffer and buffer_len + addition > CHUNK_SIZE:
            emit()
            buffer = []
            buffer_len = 0
            addition = len(frag_text)
        buffer.append((frag_text, page))
        buffer_len += addition

    if buffer:
        emit()

    return chunks


def chunk_pdf(doc: pymupdf.Document) -> list[Chunk]:
    blocks = _extract_blocks(doc)
    fragments = _split_oversized(blocks)
    lookup_section = _build_toc_section_lookup(doc.get_toc())
    return _pack_chunks(fragments, lookup_section)


def save_chunks(chunks: list[Chunk], path: str | Path) -> None:
    Path(path).write_text(json.dumps(chunks, ensure_ascii=False, indent=2))


def load_chunks(path: str | Path) -> list[Chunk]:
    return json.loads(Path(path).read_text())
