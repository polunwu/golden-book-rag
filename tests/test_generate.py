"""services.generate pure functions — refusal floor + language-matched text."""
from __future__ import annotations

from services.generate import refusal_text, should_refuse
from services.retrieval import ChunkHit


def _hit(distance: float) -> ChunkHit:
    return ChunkHit(
        chunk_index=0, text="x", page_start=1, page_end=1,
        section_path=None, section_title=None, section_level=None,
        distance=distance,
    )


def test_should_refuse_empty():
    assert should_refuse([], 0.55) is True


def test_should_refuse_below_floor():
    # best score = 1 - 0.5 = 0.50 < 0.55
    assert should_refuse([_hit(0.50)], 0.55) is True


def test_should_refuse_at_or_above_floor():
    # best score = 1 - 0.45 = 0.55, not below floor
    assert should_refuse([_hit(0.45)], 0.55) is False


def test_should_refuse_uses_best_hit_only():
    # hits[0] is best (ascending distance); 0.30 -> score 0.70 >= floor
    assert should_refuse([_hit(0.30), _hit(0.90)], 0.55) is False


def test_refusal_text_cjk():
    assert "找不到相關內容" in refusal_text("什麼是檢索增強生成？")


def test_refusal_text_latin():
    assert "couldn't find relevant content" in refusal_text("How do I bake bread?")
