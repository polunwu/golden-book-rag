---
shaping: true
---

# Step 7: V1 Implementation Plan — Grounded `/ask`

Implements **V1** from [slices.md](./slices.md) — all of Shape A: grounded
generation (`generate_answer`, A1), the refusal floor (`should_refuse` /
`refusal_text`, A2), the `POST /books/{id}/ask` handler (A3), schemas (A4), env
config readers (A5), and tests (A6).

Demo: `curl` a `ready` book's `/ask` → grounded answer with inline `[n]`
citations + numbered sources; an out-of-scope query → `refused=true` answer with
no Gemini call; `404`/`409`/`422` on the edges.

No new deps (uses `google-genai`, already present), no migration — schema
unchanged from Step 6.

## Files

| File                       | Action                                                                                       |
|----------------------------|----------------------------------------------------------------------------------------------|
| `services/generate.py`     | Create — prompt template, `generate_answer` (A1), `should_refuse` + `refusal_text` (A2), env readers (A5) |
| `api/schemas.py`           | Add `AskRequest`, `Citation`, `AskResponse` (A4)                                              |
| `api/routers/books.py`     | Add `POST /{book_id}/ask` handler + imports + `_score_floor` reader (A3/A5)                   |
| `.env.example`             | Add `GEMINI_GEN_MODEL`, `ASK_SCORE_FLOOR`, `ASK_MAX_OUTPUT_TOKENS`                            |
| `tests/conftest.py`        | Extend `_no_gemini` to stub `books.generate_answer` (A6)                                      |
| `tests/test_generate.py`   | Create — pure unit tests for `should_refuse` + `refusal_text` (A6)                            |
| `tests/test_ask.py`        | Create — 404 / 409 / 422 / grounded-200 / refusal-floor-200 (A6)                              |

---

## 1. `services/generate.py` — new module

Grounded generation + the refusal floor. Reuses `make_client` and the retry
conventions from `services/embeddings.py` (R3.3) — no second client setup. The
language pick for refusals reuses `embeddings._is_cjk` (one source of CJK ranges;
cross-module reuse within the `services` package, same pattern as `ChunkBase`).

```python
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
```

Notes:
- `should_refuse` reads `hits[0].distance` — `search_chunks` returns hits ordered
  by ascending distance, so `hits[0]` is the best (highest score). Matches the
  Step-6 `score = 1 - distance` convention.
- `_is_retryable` / `_is_cjk` are imported from `embeddings` (private, but
  intentional single-source reuse — same package, same rationale as sharing
  `ChunkBase` via `services/types.py`). If a reviewer objects, promote both to
  public names in a follow-up; not blocking V1.
- `generate_answer` wears the **same** retry decorator config as
  `embed_batch_call` (R3.3) — 5 attempts, exp backoff, retry on 429/ServerError.
- **Thinking is OFF by default** (`thinking_budget=0`). gemini-2.5-* are thinking
  models and thinking tokens are billed against `max_output_tokens`; leaving
  thinking on its dynamic default could consume the whole budget and return empty
  `resp.text` (→ the RuntimeError above). Invariant if you enable it: keep
  `ASK_MAX_OUTPUT_TOKENS > ASK_THINKING_BUDGET + expected answer length`.

---

## 2. `api/schemas.py` — ask models

`AskRequest` subclasses `SearchRequest` (F2 — identical `{query, k}` validation,
no drift). `Citation` extends the shared `ChunkBase` with the inline `marker`
number + `score`. Add after the search models:

```python
class AskRequest(SearchRequest):
    pass


class Citation(ChunkBase):
    marker: int
    score: float


class AskResponse(BaseModel):
    book_id: UUID
    query: str
    k: int
    answer: str
    refused: bool
    citations: list[Citation]
```

No new imports — `BaseModel`, `Field`, `field_validator`, `UUID`, `ChunkBase` are
already imported for the search models.

---

## 3. `api/routers/books.py` — `POST /{book_id}/ask`

Add imports:

```python
from api.schemas import (
    AskRequest, AskResponse, BookList, BookOut, ChunkOut, ChunkPage, Citation,
    SearchHit, SearchRequest, SearchResponse, UploadBookForm, UploadResponse,
)
from services.generate import generate_answer, refusal_text, should_refuse
```

Add the env reader near `_max_upload_bytes` / `_upload_dir`:

```python
def _score_floor() -> float:
    return float(os.environ.get("ASK_SCORE_FLOOR", "0.55"))
```

Add the handler after `search_book` (keeps the query endpoints together):

```python
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
```

- Gate is a verbatim copy of `search_book`'s — 404 before 409, both before any
  embed/LLM work (R2.1). (Both handlers now run the same `SELECT status` gate; if
  a third query endpoint lands, factor it into a `_require_ready(conn, book_id)`
  helper — not worth it for two.)
- `marker` is `1..k`, matching the `[n]` markers the model is told to emit (N9).
- `_score_floor` is read per-request (like `_upload_dir`), so tests can override
  `ASK_SCORE_FLOOR` via env.

---

## 4. `.env.example` — generation config

Append:

```
GEMINI_GEN_MODEL=gemini-2.5-flash
ASK_SCORE_FLOOR=0.55
ASK_MAX_OUTPUT_TOKENS=1024
ASK_THINKING_BUDGET=0
```

`ASK_THINKING_BUDGET=0` disables Gemini thinking (extractive RAG doesn't need it,
and thinking tokens share the `max_output_tokens` budget). If raised, raise
`ASK_MAX_OUTPUT_TOKENS` above it too.

---

## 5. `tests/conftest.py` — stub generation

The handler calls the real `generate_answer` (Gemini) unless stubbed. Add a
deterministic fake and patch the name bound in the router (same pattern as
`embed_query`). `should_refuse` / `refusal_text` are pure — left real.

Add near `_fake_embed_query`:

```python
def _fake_generate_answer(query: str, hits: list) -> str:
    # Deterministic, no network. Emits an inline marker so citation wiring is
    # exercised; mirrors the query language loosely (test asserts structure,
    # not phrasing).
    return f"Stub answer for {query!r}, grounded in the excerpts [1]."
```

Extend `_no_gemini`:

```python
@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.routers.books as books_mod
    import services.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "embed_chunks", _fake_embed_chunks)
    monkeypatch.setattr(books_mod, "embed_query", _fake_embed_query)
    monkeypatch.setattr(books_mod, "generate_answer", _fake_generate_answer)
```

---

## 6. `tests/test_generate.py` — pure units (no DB, no Gemini)

```python
"""services.generate pure functions — refusal floor + language-matched text."""
from __future__ import annotations

from services.generate import refusal_text, should_refuse
from services.types import ChunkBase


class _Hit(ChunkBase):
    distance: float


def _hit(distance: float):
    return _Hit(
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
```

`ChunkHit` is structurally `ChunkBase + distance`; the local `_Hit` mirrors it so
the unit tests don't need a DB row. (Alternatively import `ChunkHit` from
`services.retrieval` directly — either works; `ChunkHit` import is cleaner, use
that if it doesn't drag DB imports. `services.retrieval` imports only psycopg +
numpy at module load, so `from services.retrieval import ChunkHit` is fine — use
it and drop `_Hit`.)

---

## 7. `tests/test_ask.py` — handler (gating + grounded + refusal)

```python
"""POST /books/{id}/ask — gating, grounded answer, refusal floor.

Gemini is stubbed (conftest._no_gemini): _fake_embed_query == chunk_index 0's
stored vector (top hit, distance ~0 -> score ~1.0), and generate_answer returns
a fixed cited string. Refusal is forced by raising ASK_SCORE_FLOOR above 1.0.
"""
from __future__ import annotations

import uuid
from unittest.mock import Mock

from tests._helpers import make_pdf_bytes, upload


def _ready_book(client, book_ids, *, title="askable") -> uuid.UUID:
    resp = upload(client, book_ids, content=make_pdf_bytes(title), title=title)
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "ready"
    return bid


# --- gating -------------------------------------------------------------

def test_ask_unknown_book_404(client):
    resp = client.post(f"/books/{uuid.uuid4()}/ask", json={"query": "x"})
    assert resp.status_code == 404


def test_ask_not_ready_409(client, book_ids):
    resp = upload(client, book_ids, content=b"", title="broken")  # zero-byte -> failed
    assert resp.status_code == 202
    bid = book_ids[-1]
    assert client.get(f"/books/{bid}").json()["status"] == "failed"
    resp = client.post(f"/books/{bid}/ask", json={"query": "x"})
    assert resp.status_code == 409
    assert "status=failed" in resp.json()["detail"]


def test_ask_empty_query_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/ask", json={"query": ""}).status_code == 422
    assert client.post(f"/books/{bid}/ask", json={"query": "   "}).status_code == 422


def test_ask_k_out_of_range_422(client, book_ids):
    bid = _ready_book(client, book_ids)
    assert client.post(f"/books/{bid}/ask", json={"query": "x", "k": 0}).status_code == 422
    assert client.post(f"/books/{bid}/ask", json={"query": "x", "k": 21}).status_code == 422


# --- grounded happy path ------------------------------------------------

def test_ask_grounded_200(client, book_ids):
    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/ask", json={"query": "anything", "k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == str(bid)
    assert body["refused"] is False
    assert body["answer"]  # non-empty (stubbed)
    cites = body["citations"]
    assert 1 <= len(cites) <= 5
    # markers are 1..N in order; scores descending; citation metadata present
    assert [c["marker"] for c in cites] == list(range(1, len(cites) + 1))
    assert cites[0]["score"] == max(c["score"] for c in cites)
    assert "text" in cites[0] and "page_start" in cites[0]


# --- refusal floor ------------------------------------------------------

def test_ask_refusal_floor_no_generation(client, book_ids, monkeypatch):
    """Floor above 1.0 forces refusal; generation must NOT be called."""
    import api.routers.books as books_mod
    spy = Mock(side_effect=AssertionError("generate_answer must not be called"))
    monkeypatch.setattr(books_mod, "generate_answer", spy)
    monkeypatch.setenv("ASK_SCORE_FLOOR", "1.5")

    bid = _ready_book(client, book_ids)
    resp = client.post(f"/books/{bid}/ask", json={"query": "anything"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert body["answer"]  # language-matched refusal string
    spy.assert_not_called()
```

---

## Implementation Order

1. **`services/generate.py`** (§1) — prompt + `generate_answer` + `should_refuse`
   + `refusal_text` + env readers. `python -c "import services.generate"` to
   confirm imports resolve (incl. the private `_is_cjk` / `_is_retryable` reuse).
2. **`api/schemas.py`** (§2) — add the three models.
3. **`api/routers/books.py`** (§3) — add the handler + imports + `_score_floor`.
4. **`.env.example`** (§4) — three vars.
5. **`tests/conftest.py`** (§5) — stub `generate_answer`.
6. **`tests/test_generate.py`** + **`tests/test_ask.py`** (§§6–7) — `pytest`.
7. **Manual `curl` smoke** — boot `uvicorn`, upload a real book to `ready`:
   - EN: `{"query":"What is RAG?"}` → grounded answer with `[n]` markers + citations
   - ZH: `{"query":"什麼是檢索增強生成？"}` → Chinese answer (language mirror)
   - OOS: `{"query":"How do I bake sourdough?"}` → `refused=true`, no citations
   - edges: unknown id 404, non-ready 409, blank/k-bound 422
8. **Boundary grep** — `grep -rn "fastapi" services/` returns nothing (R3.2).

---

## Done When

- `POST /books/{id}/ask` on a `ready` book: `200`, non-empty `answer`,
  `refused=false`, `citations[]` of ≤`k` numbered sources (marker `1..k`,
  descending `score`, each with text + page/section)
- Best hit `score < ASK_SCORE_FLOOR` → `200`, `refused=true`, language-matched
  refusal `answer`, `citations:[]`, and `generate_answer` not called
- CJK query → CJK refusal; Latin query → English refusal (`refusal_text` unit)
- `404` unknown id; `409` non-`ready` (detail names status); `422` blank `query`
  or `k ∉ [1,20]` — all before embed/LLM work
- `pytest` green with no network (embed + generate stubbed, R5.1)
- `grep` finds no FastAPI import in `services/` (R3.2)
- No streaming, multi-book, rerank, history, or answer-quality eval introduced
  (Step 8+ scope)

## Step 8 Hand-off

Carried forward (see [shaping.md](./shaping.md) "Out of Scope"):

- **Answer-quality eval** is the strongest next step — `eval/` is still
  retrieval-only; `/ask` correctness is curl-verified, not measured. LLM-judge /
  RAGAS over `eval/cases.json` (faithfulness + answer-relevance) would close it.
- **Refusal floor (0.55) is corpus/model-calibrated** — re-measure if the book
  set, embedding model, or `task_type` changes.
- **Thinking is OFF (`ASK_THINKING_BUDGET=0`)** — if Step-8 answer-eval shows
  cross-chunk synthesis answers are weak, enable a small budget (e.g. 512) and
  bump `ASK_MAX_OUTPUT_TOKENS` above `budget + answer length`.
- **Faithful citation filtering** (Shape B structured output) when a consumer
  needs strict per-claim attribution; today `citations` lists all `k` sources.
- **`_is_cjk` / `_is_retryable` are reused privately** across `services/`; promote
  to public if a third consumer appears.
- **`processing`-stuck sweep** still unaddressed — a crashed-mid-ingest book
  returns 409 from `/ask` (same as `/search`).
