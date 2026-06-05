import os
from dataclasses import dataclass

from google.genai import types
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from services.embeddings import _is_cjk, _is_retryable, make_client
from services.retrieval import ChunkHit

PLAIN_SYSTEM_INSTRUCTION = (
    "You are a knowledgeable assistant. Answer the question directly from your\n"
    "own general knowledge — no book excerpts are provided, so do NOT cite.\n"
    "Answer in the same language as the question. Be concise and direct."
)

SYSTEM_INSTRUCTION = (
    "You answer questions strictly from the provided book excerpts.\n"
    "Return JSON matching the schema. Set can_answer=false when the excerpts do\n"
    "not contain enough information to answer the question, and leave answer empty\n"
    "— do NOT write a 'not enough information' sentence yourself. Otherwise set\n"
    "can_answer=true and put the grounded answer in answer.\n"
    "\n"
    "ALWAYS write `answer` in the SAME LANGUAGE AS THE QUESTION, even when the\n"
    "excerpts are in a different language. The excerpts are source material only —\n"
    "they do NOT decide the answer's language; the question does.\n"
    "\n"
    "Rules for answer when can_answer=true:\n"
    "- Use ONLY the information in the numbered excerpts. Do not use outside knowledge.\n"
    "- Support each claim with inline citation markers like [1], [2] referring to the excerpt numbers.\n"
    "- Be concise and direct."
)


class GroundedAnswer(BaseModel):
    """Structured model verdict. `can_answer=False` is the model-side soft refusal
    (excerpts retrieved but insufficient) — distinct from the pre-LLM floor refusal.
    Replaces free-form 'say so plainly' prose so the refusal is a reliable, typed
    signal rather than something the caller has to detect from the answer text."""

    can_answer: bool
    answer: str


@dataclass
class AnswerResult:
    """The /ask outcome after both refusal gates. On refusal `answer` is the
    language-matched refusal string and `cite_hits` is empty, so hard and soft
    refusals share one contract."""

    refused: bool
    answer: str
    cite_hits: list[ChunkHit]


def _gen_model() -> str:
    return os.environ.get("GEMINI_GEN_MODEL", "gemini-2.5-flash")


def _max_output_tokens() -> int:
    return int(os.environ.get("ASK_MAX_OUTPUT_TOKENS", "1024"))


def _thinking_budget() -> int:
    # gemini-2.5-* are thinking models; thinking tokens count against
    # max_output_tokens. Default 0 = thinking OFF — this is extractive grounded
    # RAG (shallow reasoning), so the full output budget goes to the answer.
    # Raise (and raise ASK_MAX_OUTPUT_TOKENS above it) if cross-chunk synthesis
    # answers degrade.
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


def _language_directive(query: str) -> str:
    """Explicit language instruction appended to the user turn. A directive at the
    end of the prompt holds against the pull of (often English) excerpts better
    than a system-instruction line. CJK query → Chinese directive (mirrors
    refusal_text's convention); otherwise English."""
    if any(_is_cjk(c) for c in query):
        return "請務必使用與問題完全相同的語言作答。"
    return "Write your answer in the same language as the question."


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
def generate_answer(query: str, hits: list[ChunkHit]) -> GroundedAnswer:
    """Single-shot grounded generation over the retrieved hits. Caller guarantees
    `hits` is non-empty and above the refusal floor. Returns a structured verdict:
    `can_answer=False` is the model-side soft refusal."""
    client = make_client()
    contents = f"{_format_context(hits)}\n\nQuestion: {query}\n\n{_language_directive(query)}"
    resp = client.models.generate_content(
        model=_gen_model(),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0,
            max_output_tokens=_max_output_tokens(),
            thinking_config=types.ThinkingConfig(thinking_budget=_thinking_budget()),
            response_mime_type="application/json",
            response_schema=GroundedAnswer,
        ),
    )
    parsed = resp.parsed
    if not isinstance(parsed, GroundedAnswer):
        raise RuntimeError("Gemini returned no structured answer")
    parsed.answer = parsed.answer.strip()
    return parsed


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def generate_plain_answer(query: str) -> str:
    """No-retrieval baseline: answer from the model's own knowledge, with no book
    context and no citations. Lets the UI compare a RAG-grounded answer against a
    plain-LLM answer for the same question. Never refuses — there is no floor and
    no excerpts to judge."""
    client = make_client()
    resp = client.models.generate_content(
        model=_gen_model(),
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=PLAIN_SYSTEM_INSTRUCTION,
            temperature=0,
            max_output_tokens=_max_output_tokens(),
            thinking_config=types.ThinkingConfig(thinking_budget=_thinking_budget()),
        ),
    )
    text = resp.text
    if text is None:
        raise RuntimeError("Gemini returned no answer")
    return text.strip()


def decide_answer(query: str, hits: list[ChunkHit], floor: float) -> AnswerResult:
    """Single decision point for /ask: applies both refusal gates and picks the
    response text. Gate 1 (cheap, no LLM): retrieval below `floor`. Gate 2: the
    model judged the excerpts insufficient (can_answer=False). Either gate -> a
    language-matched refusal with no citations, so hard and soft refusals share one
    contract (refused=True => citations=[] => message in the query's language)."""
    if should_refuse(hits, floor):
        return AnswerResult(refused=True, answer=refusal_text(query), cite_hits=[])
    g = generate_answer(query, hits)
    if not g.can_answer:
        return AnswerResult(refused=True, answer=refusal_text(query), cite_hits=[])
    return AnswerResult(refused=False, answer=g.answer, cite_hits=hits)
