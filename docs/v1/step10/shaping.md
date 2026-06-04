---
shaping: true
---

# Step 10: Ask — ask panel, answer rendering, citations, refusal state — Shaping

Step 9 shipped the **Library**: `/` lists books newest-first as navigation-only
cards (title + `<StatusBadge/>` + date) linking to `/books/{id}`, with
loading/error/empty states and an `impeccable` pass. The book page itself is
still the Step 8 placeholder ("Book {id} (coming soon)."). Step 10 turns that
placeholder into the real **book page** and builds the **Ask panel** — the heart
of the product (`frontend_mvp.md`: "Ask is shaped early — it is the heart of the
product, so prove the core value before polishing the upload/library chrome").

Step 10 is the **Ask** slice (per `frontend_mvp.md` "Shaping Steps"):
`Ask   ask panel, answer rendering, citations, refusal state`. Shape it against a
`ready` book seeded directly via the API (Upload is Step 12).

Carried in from `frontend_mvp.md` (verbatim drivers):

- Step 10 = `Ask   ask panel, answer rendering, citations, refusal state`.
- Screen 3 Ask panel: Question input + optional `k` control (default 5; backend
  1–20); `POST /books/{id}/ask`; render `answer` with clickable `[n]` markers
  that scroll to / open the matching citation; Citations list (marker, section
  breadcrumb `section_path`, page range, score, expandable chunk text); refusal
  state styling when `refused`; Loading + error (incl. `409 not ready`) states.
- Success criteria: "can see the answer produced *with* RAG retrieval and the
  answer produced *without* the retrieval process (plain LLM), side by side for
  comparison."
- `refused: true` is a first-class UI state, not an error — render the answer
  text *and* signal the refusal; `refused=True ⇒ citations=[]`.
- Screen 2 Book page (`/books/{id}`): Header (title, status, …); Primary = Ask
  panel. (Counts/Browse = Step 11; Delete = Step 14.)
- "Each gets its own shape-up + `impeccable` pass."
- Discipline carried from the backend MVP: **ship the core loop first, leave the
  seams for later.**

## Settled decisions (pre-shape forks)

Resolved with the user before/at shaping (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | **RAG-vs-plain comparison** | **Compare toggle by the Ask button.** A "compare with plain LLM" toggle sits next to the input and is chosen *before* asking. **Off** (default) → one RAG call (`?retrieve=true`), single answer column. **On** → fire both `?retrieve=true` and `?retrieve=false`, render the grounded answer and the plain-LLM answer **side by side**. The plain column only exists when compare is on — no wasted second call otherwise. (Considered: always side-by-side — rejected, doubles every LLM call unconditionally; after-the-fact "compare" button under the answer — rejected, the up-front toggle is simpler and makes the comparison a deliberate choice; RAG-only this step — rejected, the side-by-side comparison is a stated Step 10 success criterion.) |
| D2 | **Book-page header scope** | **Minimal: title + status badge.** The `/books/{id}` header = null-safe title + reused `<StatusBadge/>`. **No page/chunk count** (needs the chunks endpoint — rides Step 11) and **no Delete** (Step 14). Mirrors Step 9's restraint: build the page enough to host Ask, leave the action/count seams for their owning steps. |
| D3 | **Citation display** | **Full list at the bottom of the answer, always visible.** Each citation renders its `marker`, section breadcrumb (`section_path`), page range, score, **and full chunk text** — **no expand, no hover/popover**. Optimized for readability; the chunk text is the receipt, so it is shown, not hidden behind interaction. (Diverges from `frontend_mvp.md`'s "expandable chunk text" — the user chose always-visible over expandable.) |
| D4 | **Marker interaction** | **Click `[n]` → scroll to + highlight the matching citation.** The `[n]` markers inside the answer text are clickable; clicking scrolls the corresponding citation into view and briefly highlights it. (Not a popover/expander — D3 keeps the citation always-visible; the marker is a jump-link for long answers.) |
| D5 | **`k` control** | **Hidden, fixed `k=5`.** The ask sends the backend default `k=5`; no UI control this step. Keeps the panel clean; the `k`-control seam stays reserved (the `AskRequest`/`SearchRequest` zod schema already carries the 1–20 bound + default 5 for when it surfaces). |
| D6 | **Book page data path** | **Client component, `getBook` via TanStack Query.** `/books/{id}` becomes a `"use client"` component fetching `GET /books/{id}` through `useQuery(['book', id], …)` for the header title + status and to **gate** the Ask input on `status === 'ready'`. Refetch on mount/focus (no `setInterval` polling — that is `useBookStatus`, Step 13). The status gate mirrors the backend `409`. |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A real **book page** at `/books/{id}` (minimal title+status header) hosting an **Ask panel**: type a question → grounded answer with inline `[n]` citation markers, a full always-visible citations list, a first-class **refusal** state, and an opt-in **side-by-side plain-LLM comparison** — with loading/error states — finished with an `impeccable` pass | Core goal |
| **R1** | **Book page host** | Must-have |
| R1.1 | `/books/{id}` fetches `GET /books/{id}` and renders a **minimal header**: null-safe title + reused `<StatusBadge/>` (D2/D6) | Must-have |
| R1.2 | The Ask input is **gated on `status === 'ready'`**; when not ready, ask is disabled with a reason (mirrors backend `409`) (D6) | Must-have |
| R1.3 | Header/page **loading and error** states (book not found `404`, backend down) reuse the Step 8 primitives | Must-have |
| **R2** | **Ask request** | Must-have |
| R2.1 | Question **input + Ask action**; submits `POST /books/{id}/ask` with `{query, k:5}` via a TanStack Query **mutation**; `k` fixed at 5, no UI (D5) | Must-have |
| R2.2 | A **"compare with plain LLM" toggle** by the Ask button (D1); when on, the submit also fires `POST /books/{id}/ask?retrieve=false` | Must-have |
| R2.3 | Ask **loading** (in-flight) and **error** states, including `409 not ready` surfaced via `ApiError` | Must-have |
| **R3** | **Answer rendering** | Must-have |
| R3.1 | Render the `answer` text, parsing inline `[n]` tokens into **clickable markers** (D4) | Must-have |
| R3.2 | **Refusal** is a first-class state: when `refused`, render the answer text *and* a clear refusal signal; citations are empty (`refused ⇒ citations=[]`) | Must-have |
| R3.3 | **Compare layout**: with the toggle off, one answer column (with retrieval); with it on, **two columns side by side** — "with retrieval" (answer + markers + citations) and "without retrieval" (plain answer, **no citations**) (D1) | Must-have |
| **R4** | **Citations** | Must-have |
| R4.1 | Below the (retrieval) answer, a **full citations list**, always visible — **no expand/hover** (D3); each shows `marker`, section breadcrumb (`section_path`), page range (`page_start`–`page_end`), `score`, and full chunk `text` | Must-have |
| R4.2 | Each citation is a **scroll/highlight target** for its `[n]` marker (D4) | Must-have |
| **R5** | **Marker → citation interaction** | Must-have |
| R5.1 | Clicking `[n]` in the answer **scrolls to + briefly highlights** citation `n` in the list (D4) | Must-have |
| **R6** | **Polish** | Must-have |
| R6.1 | An **`impeccable` pass** on the Ask experience: input/toggle affordance, answer typography + marker styling, the side-by-side compare layout, citation cards (breadcrumb/page/score/text legibility), refusal + loading + error states | Must-have |
| **R7** | **Reuse the existing seams** | Must-have |
| R7.1 | Reuse the typed client (`request<T>` + `ApiError`), the existing `ask.ts` zod schemas (`AskRequest`/`AskResponse`/`Citation`) and `BookOut`, `<StatusBadge/>`, and the loading/error primitives; add only `getBook()`/`ask()` to `api/books.ts` — **no new schema** (all shapes exist) | Must-have |
| **R8** | **Scope boundaries** | Must-have |
| R8.1 | **No chunk browser / raw search** (Step 11) — Ask only; the book page has no Browse tab yet | Must-have |
| R8.2 | **No page/chunk count** in the header (Step 11), **no Delete** (Step 14), **no Upload** (Step 12) | Must-have |
| R8.3 | **No live status polling** — `getBook` refetches on mount/focus only; no `useBookStatus`/`setInterval` (Step 13) | Must-have |
| R8.4 | **No `k` UI control** (D5); **no expandable/hover citation** behavior (D3) | Must-have |
| R8.5 | **No auth / owner-scoping** — global `GET /books/{id}` and `/ask` as today; the auth seam stays reserved | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **`app/books/[id]/page.tsx` is a placeholder** — server component, `await params`, renders "Book {id} (coming soon).". Step 10 replaces it with the real book page (D6) |
| C0.2 | **`ask.ts` schemas exist** (`src/api/schemas/ask.ts`) — `AskRequest` (= `SearchRequest`: `{query, k:1..20 default 5}`), `Citation` (`ChunkBase` + `marker` + `score`), `AskResponse` (`book_id, query, k, answer, refused, citations[]`). No new schema needed (R7.1) |
| C0.3 | **`BookOut` schema exists** (`src/api/schemas/book.ts`) — feeds `getBook`'s header; `BookStatus` enum drives the gate (D6) |
| C0.4 | **Typed client exists** (`src/api/client.ts`) — `request<T>(path, schema, init?)` (JSON in/out, zod-parse, `ApiError` on non-2xx incl. the `409`/`404` friendly map). `api/books.ts` has `listBooks()` only; `getBook`/`ask` are added against `request` |
| C0.5 | **Shared primitives + badge exist** — `<Loading/>`, `<ErrorState/>`, `<Empty/>`, and `<StatusBadge status/>` (Step 9, reusable). The header reuses `<StatusBadge/>` |
| C0.6 | **Backend `/ask` contract** — `POST /books/{id}/ask` body `{query,k}`, query param `?retrieve` (default true); `?retrieve=false` → plain-LLM baseline (`refused=false`, `citations=[]`, skips the ready gate). `409` if not `ready` (retrieval path). Two refusal gates collapse into `refused=true ⇒ citations=[]` |

## A: Gated book page + Ask panel with opt-in compare (selected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Book page** — `app/books/[id]/page.tsx` becomes `"use client"`; `useQuery(['book', id], () => getBook(id))`; renders header (null-safe title + `<StatusBadge status/>`), `<Loading/>`/`<ErrorState/>` for the fetch, and hosts `<AskPanel/>`. Passes `status` down to gate ask (D2/D6) | |
| **A2** | **`getBook()` + `ask()`** in `src/api/books.ts` — `getBook(id)` → `request('/books/'+id, BookOut)`; `ask(id, {query,k}, retrieve)` → `request('/books/'+id+'/ask'+(retrieve?'':'?retrieve=false'), AskResponse, {method:'POST', body: JSON.stringify({query,k})})`. Reuses `request<T>` + existing zod (R7.1) | |
| **A3** | **`<AskPanel/>`** — question `<input>`, a **"compare with plain LLM"** toggle, and **Ask** button (disabled unless `status==='ready'` and non-empty query). `useMutation`: always `ask(id,{query,k:5},true)`; if compare on, also `ask(id,{query,k:5},false)` (both in one mutation via `Promise.all`). Holds in-flight/error state, renders `<AnswerView/>`(s) (A4) | |
| **A4** | **`<AnswerView answer refused citations?/>`** — renders the answer text with `[n]` parsed into clickable markers (A6); refusal styling + signal when `refused` (R3.2); takes citations (the retrieval column) or none (the plain column). Two `<AnswerView/>`s side-by-side when compare is on, one otherwise (R3.3) | |
| **A5** | **`<Citations citations/>`** — full, always-visible list under the retrieval answer; each item: `marker`, `section_path` breadcrumb, `page_start`–`page_end`, `score`, full `text`; each item carries an id/ref so a marker can target it (D3/R4) | |
| **A6** | **Marker parse + scroll/highlight** — split `answer` on `[n]` tokens; render each as a button that, on click, scrolls its citation into view + flashes a highlight (e.g. `ref`/`scrollIntoView` + transient class) (D4/R5) | |
| **A7** | **`impeccable` pass** — input/toggle, answer typography + marker styling, the side-by-side compare grid, citation cards, refusal/loading/error states (R6.1) | |

## B: Ask panel with after-the-fact compare button (rejected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A1, A2, A4, A5, A6, A7 identical | |
| **B2** | No up-front toggle; ask runs RAG only. A **"Compare without retrieval"** button appears *under* the rendered answer; clicking it fires `ask(id,…,false)` and adds the second column on demand (a second mutation keyed off the same query) | ⚠️ |

B defers the plain call until after the user reads the RAG answer, which can feel
more natural, but it splits the comparison into two interactions and two
mutation states (the second keyed to "the last query"), adding state to keep them
in sync (what if the query changed between the two clicks?). The user chose the
**up-front toggle** (D1): the comparison is decided before asking, both calls
fire from one submit against one query, and there is no "stale second column"
problem. ⚠️ B2's "compare the last answer" coupling is the avoided complexity.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Book page + Ask panel: grounded answer, `[n]` markers, full citations, refusal state, opt-in side-by-side plain-LLM compare, loading/error, `impeccable` | Core goal | ✅ | ✅ |
| R1.1 | `/books/{id}` fetches `GET /books/{id}`; minimal header (null-safe title + `<StatusBadge/>`) | Must-have | ✅ | ✅ |
| R1.2 | Ask gated on `status==='ready'`, disabled with reason when not | Must-have | ✅ | ✅ |
| R1.3 | Page loading/error (404, backend down) reuse Step 8 primitives | Must-have | ✅ | ✅ |
| R2.1 | Question input + Ask → `POST /ask` `{query,k:5}` mutation; `k` fixed, no UI | Must-have | ✅ | ✅ |
| R2.2 | "Compare with plain LLM" toggle by the button; on → also `?retrieve=false` | Must-have | ✅ | ❌ |
| R2.3 | Ask loading/error incl. `409` via `ApiError` | Must-have | ✅ | ✅ |
| R3.1 | Answer text with inline `[n]` parsed into clickable markers | Must-have | ✅ | ✅ |
| R3.2 | Refusal first-class: answer text + refusal signal; `citations=[]` | Must-have | ✅ | ✅ |
| R3.3 | Compare layout: 1 column off / 2 columns on (plain has no citations) | Must-have | ✅ | ✅ |
| R4.1 | Full always-visible citations (marker, breadcrumb, page range, score, full text); no expand/hover | Must-have | ✅ | ✅ |
| R4.2 | Each citation is a scroll/highlight target | Must-have | ✅ | ✅ |
| R5.1 | Click `[n]` scrolls to + highlights citation n | Must-have | ✅ | ✅ |
| R6.1 | `impeccable` pass on the Ask experience | Must-have | ✅ | ✅ |
| R7.1 | Reuse client/schemas/badge/primitives; add only `getBook`/`ask`; no new schema | Must-have | ✅ | ✅ |
| R8.1 | No chunk browser / raw search (Step 11) | Must-have | ✅ | ✅ |
| R8.2 | No count / Delete / Upload | Must-have | ✅ | ✅ |
| R8.3 | No live polling (mount/focus refetch only) | Must-have | ✅ | ✅ |
| R8.4 | No `k` UI; no expandable/hover citations | Must-have | ✅ | ✅ |
| R8.5 | No auth / owner-scoping | Must-have | ✅ | ✅ |

**Notes:**
- B fails R2.2: B has no up-front compare toggle — its comparison is an
  after-the-fact button (B2), a different affordance than the toggle D1/R2.2
  specifies, with the ⚠️ "stale second column" coupling.
- A satisfies every R: gated book page + input/toggle + dual-call mutation +
  marker-linked always-visible citations + refusal + compare grid + polish,
  nothing later steps own.

## Selected Shape

**A: Gated book page + Ask panel with opt-in compare.** Decisions baked in:

1. **Book page** (A1/D6) — `"use client"`, `useQuery(['book',id], getBook)`;
   minimal title+`<StatusBadge/>` header; hosts the Ask panel; passes `status`
   to gate ask.
2. **Client** (A2/R7.1) — add `getBook()` + `ask(…, retrieve)` to `api/books.ts`
   against the existing `request<T>` + `ask.ts`/`book.ts` zod. No new schema.
3. **Ask panel** (A3/D1/D5) — input + "compare with plain LLM" toggle + Ask;
   `k=5` fixed; one mutation fires the RAG call always and the plain call when
   compare is on.
4. **Answer** (A4/R3) — answer text with clickable `[n]` markers; first-class
   refusal; 1-column / 2-column compare layout (plain column has no citations).
5. **Citations** (A5/D3/R4) — full, always-visible list (marker, breadcrumb,
   page range, score, full text); each a marker target.
6. **Marker link** (A6/D4/R5) — `[n]` click scrolls to + highlights its citation.
7. **Polish** (A7/D5) — an `impeccable` pass on the finished Ask experience.

A's one non-trivial mechanism is the **dual-call mutation + side-by-side render**
(A3/A4) and the **marker parse + scroll/highlight** (A6) — both ordinary client
work over the existing data path and schemas; no flagged unknowns.

## Out of Scope — deferred

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Chunk browser + raw search view** ("Sources" / Browse tab) | Step 10 is Ask only (R8.1) | Step 11 |
| **Page/chunk count** in header | Needs the chunks endpoint (D2/R8.2) | Step 11 |
| **Upload form + entry point** | — | Step 12 |
| **Live status polling** (`useBookStatus`, `pending`→`ready` in place) + **`failed` `error_message` panel + re-upload** | `getBook` is mount/focus-only this step (D6/R8.3) | Step 13 |
| **Delete + confirm** | No action chrome on the book page yet (R8.2) | Step 14 |
| **`k` UI control** | Fixed `k=5` (D5/R8.4); schema already carries the bound | Later (if surfaced) |
| **Auth / owner-scoping** | Seam reserved since Step 8 (R8.5) | Auth step (post-MVP) |

## Next Step

Breadboard Shape A (the `/books/{id}` client page + `getBook`/`ask` client fns +
`<AskPanel/>` + dual-call mutation + `<AnswerView/>` w/ marker parse +
`<Citations/>` + marker→citation scroll/highlight, reusing `request`/`ask.ts`/
`<StatusBadge/>`/primitives), then slice. Expect a small number of vertical
slices — e.g. V1 the working single-answer Ask (input → grounded answer +
citations + markers + refusal + gate), V2 the side-by-side compare toggle, V3 the
`impeccable` pass — with each demoed against an API-seeded `ready` book.
