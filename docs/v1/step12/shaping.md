---
shaping: true
---

# Step 12: Status — polling hook, processing/failed UX, re-upload — Shaping

Step 9 shipped the **Library**, Step 10 the **Ask** panel, Step 11 the **Upload**
modal. Step 11 deliberately left two seams (its Out of Scope): the library card
appeared `pending` but stayed frozen until a **manual refresh** (R8.2: "no live
status polling"), and `failed`/re-upload was punted (D6/R8.1: "new uploads only,
no `book_id`"). Step 12 closes both with the **Status** feature:

Carried in from `frontend_mvp.md` (verbatim drivers):

- Step 12 = `Status   polling hook, processing/failed UX, re-upload`.
- Screen 5 Processing / status: "Poll `GET /books/{id}` until `ready` or
  `failed`. Status badge: `pending`, `processing` (spinner), `ready` (enabled),
  `failed` (show `error_message`, offer re-upload). Disable ask/search until
  `ready` (mirrors backend `409`)."
- Cross-cutting **Status polling**: "one shared hook (`useBookStatus`) backing
  library badges and the book page; **stop polling at terminal states**." (Step 12
  scopes this to the **library only** — D1; the book page reads status at load.)
- Backend contract: `POST /books/upload` "re-upload by passing existing
  `book_id`"; `GET /books/{id}` "poll this for status".
- "Each gets its own shape-up + `impeccable` pass."

**Step 12 is FE-only.** Every backend piece already exists: `GET /books/{id}`
returns `BookOut` with `status` + `error_message`; the `['books']` list GET
returns all books; and `POST /books/upload` already accepts an optional `book_id`
and upserts the row to `status='pending', error_message=NULL` (the re-upload
path). No migration, no router change.

## Settled decisions (pre-shape forks)

Resolved with the user at shaping kickoff (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Polling scope** | **Library polls; the book page does not.** The shared policy drives only the library `['books']` query, so badges flip `pending→processing→ready/failed` in place (completing Step 11's deferred live flip), stopping at terminal. The **book page does not interval-poll** — the user *waits on the library* (Step 11 D3 already keeps them there post-upload), and by the time they click into a book it is almost always `ready`; the book page only needs the **correct status at load** (`['book', id]` fetches fresh on mount), not a live interval. (Considered: book page also polls — rejected by the user as unneeded; a book opened while still `processing` simply shows the processing panel and the user returns to the polling library, or refreshes, to watch it go `ready`. This diverges from `frontend_mvp.md`'s "backing the book page" — an intentional simplification.) |
| D2 | **Re-upload entry point** | **Library failed-card only — *not* the book page.** Re-upload is offered solely on a `failed` `<BookCard/>` in the library; the **book page does not re-upload** (user's call). This keeps the book page a pure status *reader* (`ready`→Ask, `processing`→panel, `failed`→`error_message` read-only) and puts retry on the **polling** library, where the re-uploaded card flips back to `pending` and updates live — no frozen view (the wrinkle a book-page re-upload would create, since the book page doesn't poll — D1). The book-page `failed` panel still shows the `error_message`, pointing the user back to the library (the `← Library` link) to retry. (Considered: book page + library card — rejected, book-page re-upload would strand the user on a non-polling `pending` view; "any status / replace anytime" — rejected, risks re-ingesting a working book.) Re-upload stays a **`failed`-only** affordance. |
| D3 | **Re-upload mechanism** | **Reuse `BookUploadDialog` with a `book_id`.** Re-upload opens the *same* Step 11 dialog/form, seeded with the existing `book_id` and the title prefilled; `uploadBook` gains an optional `book_id` arg appended to the `FormData`. One upload mechanism, minimal new code. (Considered: a dedicated lighter re-upload control — rejected, more surface to build/style for no gain; the dialog already owns the picker, guards, busy, and inline-error surface.) New uploads stay `book_id`-less (Step 11 unchanged). |
| D4 | **Poll mechanism** | **TanStack Query `refetchInterval`, not hand-rolled `setInterval`.** The "when to poll / when to stop" rule is a single shared policy fed to both queries' `refetchInterval` (a function that returns an interval while any observed book is non-terminal and `false` once all are terminal). No `useEffect`/`setInterval`, no manual timer cleanup — the cross-cutting "stop polling at terminal states" falls out of the policy. (Considered: a `useEffect` + `setInterval` calling `refetch()` — rejected, re-implements what `refetchInterval` gives for free and leaks timers.) |
| D5 | **Processing / failed surface on the book page** | **Dedicated panels, core (not deferred to `impeccable`).** `failed` showing `error_message` is an explicit screen-5 requirement, so it is a first-class panel, not polish (the retry action lives on the library — D2). While `pending`/`processing` the book page shows a clear "we're processing this" affordance rather than today's terse `AskPanel` non-ready notice. Ask stays disabled until `ready` (mirrors backend `409`). The `impeccable` pass refines these; it doesn't introduce them. |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A **Status** feature: a shared `useBookStatus` polling policy refetches the **library list** on an interval **until terminal** (`ready`/`failed`), so badges flip live; the book page reads status at load (no interval poll — D1) and gives `processing` a clear affordance and `failed` a read-only `error_message` panel; **`failed` library cards offer re-upload** (the sole re-upload entry) reusing `BookUploadDialog` with the existing `book_id`; disable Ask until `ready`; finished with an `impeccable` pass | Core goal |
| **R1** | **Status polling** | Must-have |
| R1.1 | A **shared polling policy** (`useBookStatus`) — a `refetchInterval` that returns a poll interval while any observed book is **non-terminal** (`pending`/`processing`) and **`false`** once all are terminal (`ready`/`failed`). One source of the stop rule (D4) | Must-have |
| R1.2 | **Library badges flip live**: the existing `['books']` query polls via the shared policy; cards transition `pending→processing→ready/failed` with **no manual refresh** (completes Step 11's deferred flip); polling stops when all books are terminal (D1) | Must-have |
| R1.3 | **Book page reflects current status (no interval poll)**: the `['book', id]` query reads status fresh on mount; the processing/failed panels + the Ask gate render for that status. The book page does **not** poll and does **not** mutate (D1/D2) — it is a pure status reader; the live flip is watched on the library | Must-have |
| R1.4 | **GET-only, no hand-rolled timers**: library polling uses TanStack `refetchInterval` (no `setInterval`/`useEffect` timer); cheap and self-terminating (D4) | Must-have |
| **R2** | **Processing UX (book page)** | Must-have |
| R2.1 | While `pending`/`processing`, the book page shows a clear **processing affordance** ("we're parsing/embedding — Ask unlocks when ready"), replacing the terse `AskPanel` non-ready notice; Ask **disabled** (mirrors backend `409`) (D5) | Must-have |
| **R3** | **Failed UX + re-upload entry** | Must-have |
| R3.1 | When `status=failed`, the book page shows a **read-only failed panel**: the book's `error_message`, pointing back to the library (the `← Library` link) to retry; **no in-page re-upload** (D2/D5); Ask disabled | Must-have |
| R3.2 | A **`failed` `<BookCard/>` in the library** exposes a **re-upload** affordance (the **sole** re-upload entry — D2) opening the dialog for that `book_id` | Must-have |
| **R4** | **Re-upload request** | Must-have |
| R4.1 | `uploadBook(file, title, book_id?)` — an **optional `book_id`** appended to the `FormData`; present ⇒ backend upserts the row to `pending` and clears `error_message`. New uploads omit it (Step 11 path unchanged) (D3) | Must-have |
| R4.2 | Re-upload **reuses `BookUploadDialog`/`BookUploadForm`**, opened from the failed card with the existing `book_id` + title **prefilled**; on `202`, invalidate `['books']` so the card flips back to `pending` and **library polling resumes** (D3) | Must-have |
| **R5** | **Reuse the existing seams** | Must-have |
| R5.1 | Reuse `<StatusBadge/>` (all four states already styled, `processing` already pings), `BookOut.error_message` (already `nullable().optional()` in the zod), `BookUploadDialog`/`BookUploadForm`, the typed client, and the `['books']`/`['book', id]` queries. **Add only**: the `useBookStatus` policy, the `book_id` arg on `uploadBook`, the book-page processing + failed panels, the library failed-card re-upload affordance, and the dialog's re-upload mode | Must-have |
| **R6** | **Polish** | Must-have |
| R6.1 | An **`impeccable` pass**: the processing + failed panels, the failed-card re-upload affordance, and verifying the live badge transitions read smoothly (no jarring flips) | Must-have |
| **R7** | **Scope boundaries** | Must-have |
| R7.1 | **No backend work** — `GET /books/{id}`, the `['books']` list, and the `book_id` re-upload path all already exist; Step 12 is FE-only | Must-have |
| R7.2 | **No websockets/SSE** — polling only (`refetchInterval`), per the cross-cutting concern | Must-have |
| R7.3 | **No Delete** (Step 13); **no auth / owner-scoping** (seam stays reserved) | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **Library page** `app/page.tsx` — `useQuery(['books'], listBooks)`, renders `<BookCard/>`s. **No `refetchInterval`** → a `pending` card sits frozen until a manual refresh (Step 11 R8.2 deferred this). `BookUploadDialog` already wired with `open`/`onClose`. Step 12 adds the shared `refetchInterval` (A1/A2) + the failed-card re-upload (A8) |
| C0.2 | **Book page** `app/books/[id]/page.tsx` — `useQuery(['book', id], getBook)`, **no polling**; renders `<StatusBadge>` + `<AskPanel status=…/>`. `AskPanel` gates on `ready` and shows a terse "This book is {status} — ask is available once it's ready" for every non-ready state (no `processing` vs `failed` distinction, **no `error_message`**). Step 12 **keeps the plain `['book', id]` query un-polled** (D1), reads status fresh on mount, and adds dedicated processing/failed panels (A4/A5) — a pure status reader (re-upload is library-only, A8/D2), no `refetchInterval` |
| C0.3 | **`<StatusBadge status/>`** (`components/books/StatusBadge.tsx`) — already styles all four states; `processing` already renders an animated ping. **Reused as-is** (R5.1) |
| C0.4 | **`BookOut` zod** (`api/schemas/book.ts`) — already carries `status` (enum) + `error_message: z.string().nullable().optional()`. **No schema change** (R5.1) |
| C0.5 | **`uploadBook(file, title)`** (`api/books.ts`) — builds `FormData(file, title)` → `request('/books/upload', UploadResponse, {POST})`; comment notes "New uploads only — `book_id` is a later step." Step 12 adds the optional `book_id` arg (A6) |
| C0.6 | **`BookUploadDialog`/`BookUploadForm`** (`components/books/`) — native `<dialog>`, `useMutation(uploadBook)`, `onSuccess → invalidateQueries(['books'])` + close; the form owns the picker + client guards + inline error. Step 12 adds an optional re-upload mode (seed `book_id` + prefill title) (A7) |
| C0.7 | **Backend** — `GET /books/{id}` → `BookOut` (status + error_message). `POST /books/upload` accepts optional `book_id`: `422` if not a UUID, `404` if unknown, else `INSERT … ON CONFLICT (id) DO UPDATE SET status='pending', error_message=NULL` then re-schedules ingest. **All present** (R7.1) |

## A: Shared `refetchInterval` policy + book-page panels + dialog re-upload (selected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Shared polling policy** — `useBookStatus` (e.g. `lib/status.ts`): an `isTerminal(status)` helper + a `refetchInterval` fn that returns a poll interval (~2s) while **any** observed book is non-terminal and **`false`** once all are terminal. Single source of the stop rule (D4/R1.1/R1.4) | |
| **A2** | **Library live badges** — `app/page.tsx`'s existing `['books']` `useQuery` gains `refetchInterval` from A1 (poll while *any* book non-terminal); cards flip in place; stops when all terminal. **The library is the sole polling call site** (D1/R1.2) | |
| **A3** | **Book page reads current status (un-polled)** — `app/books/[id]/page.tsx` keeps its plain `useQuery(['book', id], getBook)` (fresh on mount, refetched by A6's invalidation), **no `refetchInterval`** (D1/R1.3); it picks the panel (A4/A5) + Ask gate from that status. The live flip is watched on the library, not here | |
| **A4** | **Processing panel** — while `pending`/`processing`, the book page renders a dedicated processing affordance (heading + "parsing/embedding, Ask unlocks when ready") in place of `AskPanel`'s terse notice; Ask disabled (D5/R2.1) | |
| **A5** | **Failed panel (read-only)** — when `failed`, render the book's `error_message` and a pointer back to the library to retry (the `← Library` link already exists); **no in-page re-upload button** (D2); Ask disabled (D5/R3.1) | |
| **A6** | **`uploadBook(file, title, book_id?)`** — optional `book_id` appended to the `FormData`; present ⇒ re-upload path (backend upserts `pending` + clears `error_message`); on `202` invalidate `['books']`/`['book', id]` so the row flips to `pending` and polling resumes (D3/R4.1) | |
| **A7** | **`BookUploadDialog` re-upload mode** — dialog/form accept an optional `bookId` + initial title; in re-upload mode the form passes `book_id` to A6. New-upload mode unchanged (no `book_id`) (D3/R4.2) | |
| **A8** | **Library failed-card re-upload (sole entry)** — a `failed` `<BookCard/>` exposes a re-upload affordance opening the same dialog with that `book_id`; this is the *only* re-upload entry point (D2/R3.2) | |
| **A9** | **`impeccable` pass** — processing + failed panels, failed-card affordance, smooth live badge transitions (R6.1) | |

A's only non-trivial mechanism is the **shared `refetchInterval` policy** (and its
list-vs-single variants) — ordinary TanStack Query config over the existing data
path, schema, dialog, and badge; **no flagged unknowns**.

## B: Hand-rolled `setInterval` polling (rejected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A4–A9 identical (panels, re-upload, dialog mode, failed-card, polish) | |
| **B2** | A `useEffect` + `setInterval` on the book page / library calling `refetch()` every ~2s, cleared on terminal status and on unmount | ⚠️ |

B re-implements what `refetchInterval` provides for free and owns manual timer
lifecycle (clear on terminal, clear on unmount, avoid double-timers across
re-renders) — a leak surface for no gain. It also fights the cross-cutting
"stop polling at terminal states," which in A is a one-line `return false`. The
user chose **`refetchInterval`** (D4). ⚠️ B2's manual `setInterval` lifecycle is
the avoided complexity.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Status feature: shared polling, live badges, processing/failed panels, failed-card re-upload, dialog re-upload via `book_id`, Ask gated, `impeccable` | Core goal | ✅ | ✅ |
| R1.1 | Shared `useBookStatus` policy: poll while non-terminal, `false` at terminal | Must-have | ✅ | ✅ |
| R1.2 | Library badges flip live; stops when all terminal | Must-have | ✅ | ✅ |
| R1.3 | Book page reads current status (fresh on mount); pure reader, no interval poll | Must-have | ✅ | ✅ |
| R1.4 | GET-only, **no hand-rolled timers** (TanStack `refetchInterval`) | Must-have | ✅ | ❌ |
| R2.1 | Processing affordance on the book page; Ask disabled | Must-have | ✅ | ✅ |
| R3.1 | Book-page failed panel: read-only `error_message`, no in-page re-upload; Ask disabled | Must-have | ✅ | ✅ |
| R3.2 | Failed library card offers re-upload (sole entry) | Must-have | ✅ | ✅ |
| R4.1 | `uploadBook(file,title,book_id?)`; `book_id` ⇒ re-upload path | Must-have | ✅ | ✅ |
| R4.2 | Re-upload reuses the dialog (prefilled `book_id`+title); invalidate → re-poll | Must-have | ✅ | ✅ |
| R5.1 | Reuse badge/schema/dialog/client/queries; add only the listed pieces | Must-have | ✅ | ✅ |
| R6.1 | `impeccable` pass | Must-have | ✅ | ✅ |
| R7.1 | No backend work (FE-only) | Must-have | ✅ | ✅ |
| R7.2 | No websockets/SSE — polling only | Must-have | ✅ | ✅ |
| R7.3 | No Delete; no auth | Must-have | ✅ | ✅ |

**Notes:**
- B fails R1.4: a `useEffect`/`setInterval` is a hand-rolled timer with manual
  cleanup — exactly what R1.4 rules out. A satisfies the same polling behaviour
  declaratively via `refetchInterval`, where "stop at terminal" is `return false`.
- A and B are otherwise identical (A4–A9 ≡ B1); they differ only on the poll
  mechanism (D4), which decides the fit check.

## Selected Shape

**A: Shared `refetchInterval` policy + book-page panels + dialog re-upload.**
Decisions baked in:

1. **Shared policy** (A1/D4/R1.1) — `useBookStatus`: `isTerminal` + a
   `refetchInterval` that polls while non-terminal and returns `false` at terminal.
2. **Library live badges** (A2/D1/R1.2) — `['books']` gains the list-aware
   `refetchInterval`; cards flip in place; stop when all terminal.
3. **Book-page current status, un-polled** (A3/D1/R1.3) — plain `['book', id]`
   query (fresh on mount); no interval, no mutation — a pure status reader; the
   live flip is watched on the library.
4. **Processing panel** (A4/D5/R2.1) — clear "we're processing" affordance;
   Ask disabled.
5. **Failed panel, read-only** (A5/D2/D5/R3.1) — `error_message` + a pointer
   back to the library to retry; no in-page re-upload; Ask disabled.
6. **Re-upload request** (A6/D3/R4.1) — `uploadBook(file,title,book_id?)`; on
   `202` invalidate so the row re-enters `pending` and polling resumes.
7. **Dialog re-upload mode** (A7/D3/R4.2) — same dialog, seeded `book_id` +
   prefilled title; new-upload path unchanged.
8. **Failed-card re-upload** (A8/D2/R3.2) — a `failed` library card opens the
   same dialog for its `book_id`.
9. **Polish** (A9/R6.1) — `impeccable` pass on panels, the failed-card
   affordance, and the live transitions.

## Out of Scope — deferred

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Delete + confirm** | No book-removal chrome this step (R7.3) | Step 13 |
| **Websockets / SSE live updates** | Polling (`refetchInterval`) is the cross-cutting mechanism; real-time push is unneeded for an ingest that runs in seconds–minutes (R7.2) | Out (MVP) |
| **Re-upload from any status (replace a working book)** | Re-upload is a `failed`-only retry affordance (D2); a general "replace the file" action risks re-ingesting a healthy book | Out (MVP) |
| **Re-upload from the book page** | Re-upload is library-only (D2); a book-page re-upload would strand the user on the non-polling `pending` view (D1). The book-page failed panel is read-only, pointing to the library to retry | Out (this step) |
| **Per-book page/chunk counts in the header** (`frontend_mvp.md` screen 2) | Not a status concern; orthogonal header polish | Optional / later |
| **Auth / owner-scoping** | Seam reserved since Step 8 (R7.3) | Auth step (post-MVP) |

## Next Step

Breadboard Shape A (the shared `useBookStatus` `refetchInterval` policy applied
to `['books']` — the library only — the book-page processing/failed panels, the
`book_id` arg on `uploadBook`, the dialog re-upload mode, and the failed-card
re-upload affordance — reusing `<StatusBadge/>`/`BookOut`/`BookUploadDialog`/the
client/queries), then slice. Expect a small number of vertical slices — e.g. V1
the live library polling (badges flip to `ready` without refresh), V2 the
processing/failed panels + re-upload (`book_id`, dialog mode, failed-card), V3
the `impeccable` pass — each demoed against the running backend (upload a real
PDF and watch the **library** card flip `pending→processing→ready` live; force a
`failed` book and re-upload it from its library card → it flips back to `pending`
and polls live).
