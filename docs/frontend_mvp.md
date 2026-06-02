# BookRAG Frontend MVP

## Goal

Put a usable UI on top of the existing FastAPI BookRAG backend so a user can:

1. Upload a PDF book and watch it become searchable
2. Browse their library of uploaded books
3. Ask questions about a book and read grounded answers with citations
4. Inspect the source passages behind each answer

The backend (steps 1–7) is done. This MVP is the thin, production-minded client
that exercises every endpoint the backend already ships.

---

## Non-Goals (explicitly out for v1)

```text
auth / accounts / multi-tenant
streaming token-by-token answers
conversation history / multi-turn chat memory
in-browser PDF viewer with page rendering
reranking / hybrid-search UI controls
mobile-first / offline
admin / eval dashboards
```

Keep the same discipline as the backend MVP: ship the core loop first, leave the
seams for later.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | Next.js (App Router) + React + TypeScript | matches architecture doc's stated future FE |
| Data fetching | TanStack Query (React Query) | polling, cache, mutation states out of the box |
| Styling | Tailwind CSS | fast, plays well with `impeccable` polish pass |
| HTTP | typed `fetch` wrapper | small surface, no axios needed |
| Validation | zod (mirror backend pydantic schemas) | runtime safety at the API boundary |

> Decision to confirm during shaping: Next.js vs. a plain Vite SPA. Next.js is the
> default per the architecture doc, but the MVP has no SSR/SEO needs, so Vite is a
> legitimate lighter option.

---

## Backend Contract (already shipped — what the FE consumes)

Base path: `/books`. Status enum: `pending | processing | ready | failed`.

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| `POST` | `/books/upload` | multipart: `file` (pdf), `title`, optional `book_id` | `202 {book_id, status:"pending"}` | re-upload by passing existing `book_id`; 413 over `MAX_UPLOAD_MB` |
| `GET` | `/books` | — | `{items: BookOut[]}` | sorted newest first |
| `GET` | `/books/{id}` | — | `BookOut` | poll this for status |
| `GET` | `/books/{id}/chunks` | `?limit=50&offset=0` | `{items, total, limit, offset}` | browse parsed chunks |
| `POST` | `/books/{id}/search` | `{query, k}` | `{hits: SearchHit[]}` | `409` if not `ready` |
| `POST` | `/books/{id}/ask` | `{query, k}` `?retrieve=true` | `{answer, refused, citations[]}` | `409` if not `ready`. `?retrieve=false` → no-retrieval baseline: plain-LLM answer, `refused=false`, `citations=[]`, skips the ready gate |
| `DELETE` | `/books/{id}` | — | `204` | also deletes the PDF |

### Key response shapes

```ts
type BookOut = {
  id: string;            // uuid
  title: string | null;
  file_path: string | null;
  created_at: string;    // ISO
  status: "pending" | "processing" | "ready" | "failed";
  error_message: string | null;
};

type ChunkBase = {
  chunk_index: number;
  text: string;
  page_start: number | null;
  page_end: number | null;
  section_path: string[] | null;   // full hierarchy, good for breadcrumbs
  section_title: string | null;
  section_level: number | null;
};

type Citation = ChunkBase & { marker: number; score: number };   // marker = [1],[2]...
type SearchHit = ChunkBase & { score: number };                  // score = 1 - cosine_dist

type AskResponse = {
  book_id: string;
  query: string;
  k: number;
  answer: string;
  refused: boolean;       // soft-refuse when retrieval scores too low
  citations: Citation[];
};
```

> `refused: true` is a first-class UI state, not an error — backend deliberately
> declines to answer when no chunk clears `ASK_SCORE_FLOOR`. The UI must render the
> answer text *and* signal that it was a refusal (e.g. "Not enough in this book to
> answer confidently").

---

## Core User Journey

```text
Library
  ↓ upload PDF
Processing (pending → processing → ready/failed)   ← poll GET /books/{id}
  ↓ ready
Book page
  ↓ type a question
Ask → answer + inline citation markers [1][2]
  ↓ click a marker
Source passage (chunk text + page range + section breadcrumb)
```

---

## Screens / Components

### 1. Library (`/`)
- Grid/list of `BookOut`, newest first (`GET /books`)
- Each card: title, status badge, created date, ask/delete actions
- "Upload book" entry point
- Empty state when no books

### 2. Book page (`/books/{id}`)
- Header: title, status, page/chunk count, delete
- Primary: **Ask** panel
- Secondary tab: **Browse chunks** (`GET /books/{id}/chunks`, paginated)

### 3. Ask panel
- Question input + optional `k` control (default 5; backend allows 1–20)
- `POST /books/{id}/ask`
- Render `answer` with clickable `[n]` markers that scroll to / open the matching citation
- Citations list: marker, section breadcrumb (`section_path`), page range, score, expandable chunk text
- Refusal state styling when `refused`
- Loading + error (incl. `409 not ready`) states
- Success criteria: can see the answer produced *with* RAG retrieval and the answer produced *without* the retrieval process (plain LLM), side by side for comparison

### 4. Search (optional for v1, same plumbing as Ask)
- Reuse the query box → `POST /books/{id}/search` → ranked `SearchHit` list
- Lets us validate retrieval visually before/independently of LLM answers
- Could ship as a "Sources" toggle rather than a separate screen

### 5. Chunk browser
- Paginated table/list of `ChunkOut`
- Columns: index, page range, section breadcrumb, text preview
- Useful for debugging ingestion quality

### 6. Upload (modal or `/upload`)
- File picker (accept `application/pdf`), title field
- `POST /books/upload` → on `202`, drop the new book into the library as `pending`
- Client-side guard against oversized files before the 413 round-trips
- Surface 413 / 422 errors inline

### 7. Processing / status
- Poll `GET /books/{id}` until `ready` or `failed`
- Status badge component: `pending`, `processing` (spinner), `ready` (enabled), `failed` (show `error_message`, offer re-upload)
- Disable ask/search until `ready` (mirrors backend `409`)

---

## Cross-Cutting Concerns

- **Status polling**: one shared hook (`useBookStatus`) backing library badges and the book page; stop polling at terminal states.
- **Error model**: backend returns `{detail: string}`. One typed client that maps status codes → friendly messages (413 size, 422 validation, 404 missing, 409 not ready).
- **Empty / loading / error** states defined per screen up front (this is where the `impeccable` polish pass earns its keep).
- **Citations are the product**: trust comes from showing the receipts — invest in how `section_path` + page range + score render.

---

## Shaping Steps (each gets its own shape-up + impeccable pass)

Ask is shaped early — it is the heart of the product, so prove the core value
before polishing the upload/library chrome. Shape it against a `ready` book seeded
directly via the API.

Numbering continues from the backend MVP, which finished at Step 7.

```text
Step 8   Foundation   typed API client, zod schemas, layout shell, env config
Step 9   Library      list books, status badges, empty state
Step 10  Ask          ask panel, answer rendering, citations, refusal state
Step 11  Sources      chunk browser + (optional) raw search view
Step 12  Upload       upload form, optimistic pending card, error handling
Step 13  Status       polling hook, processing/failed UX, re-upload
Step 14  Delete       delete book + confirm
```

---

## Success Criteria (FE MVP)

The frontend MVP is successful if a user can, with no API client:

- upload a PDF and see it move pending → ready (or a clear failure)
- ask a question and get a grounded answer
- see and open the cited passages with correct page numbers
- understand when the system refuses to answer
- browse the parsed chunks of a book
- delete a book

That is a complete, honest client over the existing RAG backend.
