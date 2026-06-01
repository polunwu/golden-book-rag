import os

from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from services.embeddings import _is_cjk, _is_retryable, make_client
from services.retrieval import ChunkHit

SYSTEM_INSTRUCTION = (
    "You answer questions strictly from the provided book excerpts.\n"
    "Rules:\n"
    "- Use ONLY the information in the numbered excerpts. Do not use outside knowledge.\n"
    "- Support each claim with inline citation markers like [1], [2] referring to the excerpt numbers.\n"
    "- If the excerpts do not contain enough information to answer, say so plainly.\n"
    "- Answer in the same language as the question.\n"
    "- Be concise and direct."
)


def _gen_model() -> str:
    return os.environ.get("GEMINI_GEN_MODEL", "gemini-2.5-flash")


def _max_output_tokens() -> int:
    return int(os.environ.get("ASK_MAX_OUTPUT_TOKENS", "1024"))


def _thinking_budget() -> int:
    # gemini-2.5-* are thinking models; thinking tokens count against
    # max_output_tokens. Default 0 = thinking OFF — this is extractive grounded
    # RAG (shallow reasoning), so the full output budget goes to the answer.
    # Raise (and raise ASK_MAX_OUTPUT_TOKENS above it) if cross-chunk synthesis
    # answers degrade — see Step 8 hand-off.
    return int(os.environ.get("ASK_THINKING_BUDGET", "0"))


def should_refuse(hits: list[ChunkHit], floor: float) -> bool:
    """True when retrieval is too weak to answer: no hits, or the best hit's
    cosine score (1 - distance) is below `floor`. Pure — no model call."""
    if not hits:
        return True
    best_score = 1.0 - hits[0].distance
    return best_score < floor


def refusal_text(query: str) -> str:
    """Language-matched 'no relevant content' message (no model call). CJK
    query → Chinese; otherwise English."""
    if any(_is_cjk(c) for c in query):
        return "找不到相關內容，無法根據這本書回答這個問題。"
    return "I couldn't find relevant content in this book to answer that question."


def _cite_label(h: ChunkHit) -> str:
    parts: list[str] = []
    if h.page_start is not None:
        span = (
            f"p.{h.page_start}"
            if h.page_end in (None, h.page_start)
            else f"p.{h.page_start}-{h.page_end}"
        )
        parts.append(span)
    if h.section_title:
        parts.append(h.section_title)
    return " · ".join(parts) if parts else "source"


def _format_context(hits: list[ChunkHit]) -> str:
    blocks = [f"[{i}] ({_cite_label(h)})\n{h.text}" for i, h in enumerate(hits, start=1)]
    return "Excerpts:\n\n" + "\n\n".join(blocks)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def generate_answer(query: str, hits: list[ChunkHit]) -> str:
    """Single-shot grounded generation over the retrieved hits. Caller guarantees
    `hits` is non-empty and above the refusal floor."""
    client = make_client()
    contents = f"{_format_context(hits)}\n\nQuestion: {query}"
    resp = client.models.generate_content(
        model=_gen_model(),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0,
            max_output_tokens=_max_output_tokens(),
            thinking_config=types.ThinkingConfig(thinking_budget=_thinking_budget()),
        ),
    )
    if not resp.text:
        raise RuntimeError("Gemini returned no answer text")
    return resp.text.strip()
