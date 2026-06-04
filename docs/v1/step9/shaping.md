---
shaping: true
---

# Step 9: Library — list books, status badges, empty state — Shaping

Step 8 shipped the **Foundation**: a Next.js App Router skeleton, a typed
zod-validated `fetch` client (`request<T>`), the `ApiError` status→message map,
hand-written resource schemas, shared loading/error/empty primitives, the
layout shell, and a **connectivity smoke** at `/` ("Connected · N books") driven
by `listBooks()` through TanStack Query. Step 9 turns that smoke into the real
**Library** screen — the first feature screen, and the app's front door.

Step 9 is the **Library** slice (per `frontend_mvp.md` "Shaping Steps"):
`Library   list books, status badges, empty state`. It replaces the smoke at `/`
with a list of the user's books (newest first), each card showing title + status
badge + created date and linking to its book page, plus a populated empty state —
and (unlike Step 8) it **gets its own `impeccable` polish pass**.

Carried in from `frontend_mvp.md` (verbatim drivers):

- Step 9 = `Library   list books, status badges, empty state`.
- Screen 1 Library (`/`): grid/list of `BookOut`, newest first (`GET /books`);
  each card: title, status badge, created date, ask/delete actions; "Upload
  book" entry point; empty state when no books.
- Status badge component: `pending`, `processing` (spinner), `ready` (enabled),
  `failed` (show `error_message`, offer re-upload) — *most of this lands in its
  owning steps; see scope boundaries.*
- "Each gets its own shape-up + `impeccable` pass."
- Discipline carried from the backend MVP: **ship the core loop first, leave the
  seams for later.**

## Settled decisions (pre-shape forks)

Resolved with the user before/at shaping (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Card chrome scope** | **Navigation-only card.** Card = title + static status badge + created date; the whole card links to `/books/{id}`. **No per-card Ask/Delete buttons** — those affordances land in their owning steps (Ask = Step 10, Delete = Step 14). Mirrors Step 8's restraint: build the list, leave the action seams for the steps that own them. (Considered stubbed/disabled action buttons to show the final layout early — rejected: front-loads chrome Steps 10/14 own, untestable until then, and may drift as those steps refine their UX.) |
| D2 | **Upload entry point** | **Omit until Step 12.** No upload affordance this step; the empty state simply reads "No books yet." Books are seeded via the API for the Step 9 demo. (Considered an entry-point button routing to a `/upload` stub — rejected: Step 12 adds the entry point and the form together, so a stub now is throwaway chrome.) |
| D3 | **Badge liveness** | **Static, refetch on mount.** The badge reflects `status` from the `GET /books` fetch; TanStack Query refetches on mount/focus, but there is **no live `setInterval` polling** — that is the `useBookStatus` hook in Step 13, which makes a `pending`→`ready` transition update in place. Step 9's badge is correct at fetch time and refreshes on navigation. |
| D4 | **Route** | **Library replaces the smoke at `/`.** The Step 8 "Connected · N books" indicator is retired; `app/page.tsx` becomes the Library. The `listBooks()` endpoint and TanStack Query wiring are reused as-is. |
| D5 | **`impeccable` pass** | **Yes — Step 9 gets one** (unlike Step 8, which was structural). The Library is the front door; the polish pass rides this step per `frontend_mvp.md`. |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A **Library** screen at `/` listing the user's books newest-first from `GET /books`, each card showing title + status badge + created date and linking to its book page, with loading / error / populated-empty states — replacing the Step 8 connectivity smoke, and finished with an `impeccable` pass | Core goal |
| **R1** | **Book list fetch + states** | Must-have |
| R1.1 | Fetch `GET /books` via TanStack Query (reuse `listBooks()`), rendered **newest first** (backend already sorts; FE does not re-sort) | Must-have |
| R1.2 | **Loading / error states** reuse the Step 8 primitives (`<Loading/>`, `<ErrorState/>`); error surfaces the `ApiError` message (e.g. backend down) | Must-have |
| **R2** | **Book card** | Must-have |
| R2.1 | Card shows **title** (handle `title: null` → a sensible fallback, e.g. "Untitled" / file-derived), **status badge**, **created date** (format the ISO `created_at` for humans) | Must-have |
| R2.2 | The **whole card links to `/books/{id}`** (establishes the route; the book page is a placeholder until Step 10/11). Keyboard-focusable, accessible link | Must-have |
| **R3** | **Status badge** | Must-have |
| R3.1 | A reusable **badge component** rendering all four states (`pending`, `processing`, `ready`, `failed`) with distinct visual treatment; **static** (no polling — D3/Step 13). Built to be reused by the book page later | Must-have |
| R3.2 | `failed` state is legible as a failure; **does not** build the `error_message` detail panel or re-upload action (those ride Steps 12/13) — just the badge's failed treatment | Must-have |
| **R4** | **Empty state** | Must-have |
| R4.1 | When `GET /books` returns zero items, render a **populated empty state** ("No books yet.") via the shared `<Empty/>` primitive; **no upload affordance** (D2/Step 12) | Must-have |
| **R5** | **Polish** | Must-have |
| R5.1 | An **`impeccable` pass** on the Library: visual hierarchy, card layout, badge styling, spacing, responsive grid/list, the empty state (D5) | Must-have |
| **R6** | **Scope boundaries** | Must-have |
| R6.1 | **No Ask** (Step 10), **no Delete** (Step 14), **no Upload** (Step 12) — no per-card action buttons, no upload entry point | Must-have |
| R6.2 | **No live status polling** — no `useBookStatus`, no `setInterval` (Step 13). Badge is static per D3 | Must-have |
| R6.3 | **No `error_message` panel / re-upload** flow — `failed` is a badge state only this step (Steps 12/13) | Must-have |
| R6.4 | **No auth / owner-scoping** — the list is the global `GET /books` as today (C0.6 from Step 8); the auth seam stays reserved | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **`app/page.tsx` is the connectivity smoke** — `"use client"`, `useQuery(['books'], listBooks)`, renders `<Loading/>` / `<ErrorState/>` / "Connected · N books" badge. Step 9 replaces its render with the Library (D4) |
| C0.2 | **`listBooks()` is wired** (`src/api/books.ts`) — `GET /books` → `BookList` zod parse → returns `BookOut[]`. Reused unchanged |
| C0.3 | **`BookOut` schema exists** (`src/api/schemas/book.ts`) — `id, title (nullable), file_path (nullable), created_at, status, error_message (nullable)`; `BookStatus` enum (`pending\|processing\|ready\|failed`). No new schema needed |
| C0.4 | **Shared primitives exist** (`src/components/`) — `<Loading label/>`, `<ErrorState detail/>`, `<Empty label/>`. Library reuses; a new `<StatusBadge/>` joins them |
| C0.5 | **Layout shell + routes exist** — `app/layout.tsx` (header "Ask your book" → `/`, `<Providers>`), `app/books/[id]/page.tsx` (placeholder "Book {id} — coming soon."). Card links target this existing route |
| C0.6 | **Backend `GET /books` returns `{items: BookOut[]}` newest-first** (sorted server-side, per backend contract). FE does not sort |

## A: Navigation-only Library (selected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Library page** — `app/page.tsx` keeps `"use client"` + `useQuery(['books'], listBooks)`; replaces the smoke render with: `isLoading` → `<Loading/>`, `error` → `<ErrorState/>`, empty → `<Empty label="No books yet."/>`, else the book list (A4) | |
| **A2** | **`<StatusBadge status/>`** `src/components/StatusBadge.tsx` — maps the 4 `BookStatus` values to distinct styles/labels (e.g. `ready` green, `processing` amber + subtle spinner, `pending` zinc, `failed` red). Static, presentational, reused by the book page later | |
| **A3** | **`formatDate`** helper (`src/lib/format.ts` or inline) — ISO `created_at` → a human date (locale-aware, e.g. "Jun 2, 2026"); `null`-safe title fallback ("Untitled") | |
| **A4** | **`<BookCard book/>`** `src/components/BookCard.tsx` — `next/link` wrapping the whole card → `/books/{book.id}`; shows title (A3 fallback), `<StatusBadge/>`, created date. Focusable/accessible | |
| **A5** | **List/grid container** — maps `data` to `<BookCard/>`s in a responsive layout (grid on wide, stacked on narrow); newest-first as returned (no re-sort) | |
| **A6** | **`impeccable` pass** — polish hierarchy, card/badge styling, spacing, responsive behaviour, the empty state (R5.1) | |

## B: Library with stubbed action chrome (rejected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A1–A6 identical | |
| **B2** | Per-card **Ask** and **Delete** buttons rendered now, disabled / non-functional (or routing to stubs), to show the final card layout early | ⚠️ |
| **B3** | **"Upload book"** entry-point button (header + empty state) routing to a `/upload` stub | ⚠️ |

B front-loads the action chrome so later steps "just fill it in." But every
affordance built here is **unused until its step** (Ask = Step 10, Delete = Step
14, Upload = Step 12), **untestable** without that step's behaviour, and likely
to **drift** as those steps shape their real UX (Ask's `k` control + answer
panel, Delete's confirm, Upload's multipart + 413 guard). It's the same
speculative-chrome creep Step 8's R6.1 fenced off (⚠️ B2/B3). A already produces a
demo-able, honest Library; B's payoff is cosmetic preview only.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Library at `/`, newest-first cards (title + badge + date) linking to book page, loading/error/empty, `impeccable` pass | Core goal | ✅ | ✅ |
| R1.1 | Fetch `GET /books` via TanStack Query, newest-first (no FE re-sort) | Must-have | ✅ | ✅ |
| R1.2 | Loading/error reuse Step 8 primitives; error shows `ApiError` message | Must-have | ✅ | ✅ |
| R2.1 | Card: title (null-safe), status badge, formatted created date | Must-have | ✅ | ✅ |
| R2.2 | Whole card links to `/books/{id}`, accessible | Must-have | ✅ | ✅ |
| R3.1 | Reusable static `<StatusBadge/>` for all 4 states | Must-have | ✅ | ✅ |
| R3.2 | `failed` legible as a badge state; no detail panel/re-upload | Must-have | ✅ | ✅ |
| R4.1 | Populated empty state, no upload affordance | Must-have | ✅ | ❌ |
| R5.1 | `impeccable` pass on the Library | Must-have | ✅ | ✅ |
| R6.1 | No Ask / Delete / Upload chrome | Must-have | ✅ | ❌ |
| R6.2 | No live status polling | Must-have | ✅ | ✅ |
| R6.3 | No `error_message` panel / re-upload | Must-have | ✅ | ✅ |
| R6.4 | No auth / owner-scoping; global `GET /books` | Must-have | ✅ | ✅ |

**Notes:**
- B fails R6.1 / R4.1: B2 adds Ask/Delete chrome and B3 adds an Upload entry
  point — the action/upload affordances R6.1 and R4.1 (D2) deliberately exclude.
- A satisfies every R: list + static badge + navigation-only cards + populated
  empty state + polish, nothing later steps own.

## Selected Shape

**A: Navigation-only Library.** Decisions baked in:

1. **Page** — `app/page.tsx` stays a `"use client"` TanStack Query component;
   the smoke render is replaced by loading/error/empty/list (D4). `listBooks()`
   reused as-is.
2. **Card** — `<BookCard/>` links the whole card to `/books/{id}` (D1); shows
   null-safe title, `<StatusBadge/>`, formatted created date. **No Ask/Delete
   buttons.**
3. **Badge** — reusable static `<StatusBadge/>` for the 4 states (D3); no
   polling, no `error_message` panel.
4. **Empty** — `<Empty label="No books yet."/>`; **no upload affordance** (D2).
5. **Polish** — an `impeccable` pass on the finished Library (D5).

A has no ⚠️ unknowns: the data path (TanStack Query → `listBooks()` → `BookOut`
zod) and primitives already exist from Step 8; Step 9 adds presentational
components and a render swap.

## Out of Scope — deferred (Step 10+ hand-off)

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Ask panel** (answer + citations + refusal + RAG-vs-no-RAG) | Product's heart; own shape + `impeccable` pass | Step 10 |
| **Sources / chunk browser / raw search** | — | Step 11 |
| **Upload form + entry point** (multipart, 413 guard, optimistic pending card) | D2 omits the entry point this step | Step 12 |
| **Live status polling** (`useBookStatus`, `pending`→`ready` in place) + **`failed` `error_message` panel + re-upload** | D3/R6.2/R6.3; Step 9 badge is static | Step 13 |
| **Delete + confirm** | No per-card action chrome (D1/R6.1) | Step 14 |
| **Auth / owner-scoped library** | Seam reserved since Step 8 (C0.6) | Auth step (post-MVP) |

## Next Step

Breadboard Shape A (the `app/page.tsx` render swap + `<BookCard/>` +
`<StatusBadge/>` + `formatDate`/title fallback + responsive container + reuse of
`listBooks`/primitives), then slice. A single vertical slice is expected — one
Library screen whose demo is the rendered book list (seeded via API), with the
`impeccable` pass as the closing move.
