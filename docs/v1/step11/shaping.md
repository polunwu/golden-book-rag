---
shaping: true
---

# Step 11: Upload — upload form, optimistic pending card, error handling — Shaping

Step 9 shipped the **Library** (`/` lists books newest-first as navigation-only
cards) and Step 10 shipped **Ask** (the real `/books/{id}` page hosting the Ask
panel). Both deliberately deferred the **upload entry point** (Step 9 D2: "the
empty state simply reads 'No books yet.'; books are seeded via the API"). Step 11
closes that gap: the **Upload** feature, so a user can add a PDF without touching
the API.

Step 11 is the **Upload** slice (per `frontend_mvp.md` "Shaping Steps", after the
chunk-browser view was dropped — Upload moved from Step 12 to Step 11):
`Upload   upload form, optimistic pending card, error handling`.

Carried in from `frontend_mvp.md` (verbatim drivers):

- Step 11 = `Upload   upload form, optimistic pending card, error handling`.
- Screen 4 Upload (modal or `/upload`): file picker (accept `application/pdf`),
  title field; `POST /books/upload` → on `202`, drop the new book into the
  library as `pending`; client-side guard against oversized files before the 413
  round-trips; surface 413 / 422 errors inline.
- Backend contract: `POST /books/upload` multipart `file` (pdf), `title`,
  optional `book_id` → `202 {book_id, status:"pending"}`; re-upload by passing an
  existing `book_id`; 413 over `MAX_UPLOAD_MB`.
- Cross-cutting: one typed client maps status → friendly messages (413 size, 422
  validation); empty/loading/error states are where the `impeccable` pass earns
  its keep.
- "Each gets its own shape-up + `impeccable` pass."
- Discipline carried from the backend MVP: **ship the core loop first, leave the
  seams for later.**

## Settled decisions (pre-shape forks)

Resolved with the user at shaping kickoff (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Upload surface** | **Modal over the library.** An "Upload book" entry point on `/` opens a dialog *on top of* the library; the user never leaves the library context. On success the dialog closes and the new pending card is already there — matching `frontend_mvp.md`'s "drop the new book into the library as pending." (Considered: a dedicated `/upload` route — rejected, a context switch away from and back to the library for what is fundamentally a library action; an inline expanding panel on `/` — rejected, dilutes the focused "upload moment" and pushes form state onto the library page.) The dialog uses the native `<dialog>` element (`showModal()` gives focus-trap + Esc + backdrop for free — no a11y hand-rolling, no new dependency). |
| D2 | **Pending card mechanism** | **Invalidate + refetch — no optimistic cache write.** On `202`, `queryClient.invalidateQueries(['books'])` → the refetch shows the **real** pending row. The backend **inserts and commits** the `books` row *before* returning `202`, so the refetch reliably renders it; no synthetic/hand-built `BookOut` is ever spliced into the cache. (Considered: optimistic insert from the `202` body — rejected, the `202` carries only `{book_id, status}`, so an optimistic card would fake `title`/`created_at` until reconciliation, for a one-GET-round-trip saving the honest path already delivers.) "Optimistic" in the plan is satisfied by the card *appearing immediately on success* — it just sources from a real refetch, not a fabricated row. |
| D3 | **Post-success landing** | **Stay on the library.** After a successful upload the dialog closes and the user watches the new pending card in `/`. **No navigation to `/books/{id}`** — that page has no live status polling yet (Step 12), so routing there would strand the user on a static not-ready page with a disabled Ask until a manual refresh. Staying on the library is the honest "I uploaded, here it is" moment for this step. |
| D4 | **Title field default** | **Auto-fill from the filename, editable.** On file pick, prefill the title `<input>` from the file name (strip the `.pdf` extension); the user can edit it. Avoids the empty-title `422`, removes friction, and keeps the field honest (still a real, editable title). (Considered: blank required field — rejected, more friction and an easy way to hit the `422`.) |
| D5 | **Client-side guards** | **Type + size checked before submit.** The file `<input>` uses `accept="application/pdf"`; on pick the form rejects non-PDF (mirrors the backend `422`) and rejects files over the size cap **before** the `POST` so the 413 never round-trips (`frontend_mvp.md`: "client-side guard against oversized files before the 413"). The cap is a FE constant `MAX_UPLOAD_MB` (default **100**, optionally `NEXT_PUBLIC_MAX_UPLOAD_MB`) added to `src/lib/config.ts` next to `API_BASE_URL`, mirroring the backend default. The server `413`/`422` remain the backstop (surfaced inline) — the client guard is a courtesy, not the gate. |
| D6 | **New uploads only — no `book_id`** | **`uploadBook` never sends `book_id`.** Step 11 creates *new* books; the backend's re-upload-by-`book_id` path (and its `failed`→re-upload UX) is **Step 12**. Keeps the form single-purpose. |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | An **Upload** feature reachable from the Library: an entry point opens a **modal** with a PDF file picker + title field; submitting `POST /books/upload` creates the book and, on `202`, the new **pending** card appears in the library — with client-side type/size guards, inline error handling (413/422), and loading state — finished with an `impeccable` pass | Core goal |
| **R1** | **Entry point** | Must-have |
| R1.1 | An **"Upload book"** action on the Library (`/`) that opens the upload modal; present both when the library has books **and** in the **empty state** as its primary CTA (Step 9 left the empty state with no action — D1) | Must-have |
| **R2** | **Upload request** | Must-have |
| R2.1 | `uploadBook(file, title)` in `src/api/books.ts` builds a `FormData` (`file`, `title`) and calls `request('/books/upload', UploadResponse, {method:'POST', body: formData})`; reuses the existing `request<T>` (its `FormData` branch keeps the browser-set multipart content-type) and the existing `UploadResponse` zod — **no new schema** (R7). Never sends `book_id` (D6) | Must-have |
| R2.2 | Submit runs through a TanStack Query **mutation**; on success → `invalidateQueries(['books'])` + close dialog (D2/D3) | Must-have |
| **R3** | **Upload form** | Must-have |
| R3.1 | File `<input type="file" accept="application/pdf">` + a **title** `<Input>` **auto-filled from the filename** on pick, editable (D4) | Must-have |
| R3.2 | **Client-side guards before submit** (D5): reject non-PDF and reject files over `MAX_UPLOAD_MB` (FE constant, default 100), with inline messages; submit disabled until a valid file + non-empty title | Must-have |
| **R4** | **Pending card in the library** | Must-have |
| R4.1 | On `202`, the new **pending** book renders as a `<BookCard/>` with the existing `<StatusBadge status="pending"/>`, via `invalidateQueries(['books'])` refetch — **no optimistic/fabricated cache row** (D2) | Must-have |
| **R5** | **Error handling** | Must-have |
| R5.1 | Mutation **in-flight** state (disabled submit + busy affordance) and **error** state surfaced **inline in the dialog** via the friendly `ApiError` message: **413** (too large) and **422** (not a PDF / empty title) at minimum, plus the generic fallback (e.g. backend down) | Must-have |
| **R6** | **Polish** | Must-have |
| R6.1 | An **`impeccable` pass** on the upload experience: the entry-point button(s), the dialog (layout, the file-picker affordance, the auto-filled title field, submit), the empty-state CTA, and the in-flight + inline-error states | Must-have |
| **R7** | **Reuse the existing seams** | Must-have |
| R7.1 | Reuse the typed client (`request<T>` FormData branch + `ApiError` 413/422 map), the existing `UploadResponse` zod, `<BookCard/>` + `<StatusBadge/>`, the `Button`/`Input`/`Notice` primitives, and the `['books']` query; add only `uploadBook()` to `api/books.ts`, a `MAX_UPLOAD_MB` constant to `config.ts`, an `<UploadDialog/>`, and the entry-point wiring — **no new schema, no client change** | Must-have |
| **R8** | **Scope boundaries** | Must-have |
| R8.1 | **No re-upload / `book_id`** path, **no `failed`→re-upload UX** (Step 12) — new uploads only (D6) | Must-have |
| R8.2 | **No live status polling** — the pending card is correct at refetch time; `pending→ready` in place is `useBookStatus` (Step 12). No `setInterval` | Must-have |
| R8.3 | **No Delete** (Step 13); **no drag-and-drop** required (a file-picker `<input>` is the affordance; drag-drop, if it appears, rides the `impeccable` pass, not a must-have) | Must-have |
| R8.4 | **No auth / owner-scoping** — global `POST /books/upload` as today; the auth seam stays reserved | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **Library page** `app/page.tsx` — `"use client"`, `useQuery(['books'], listBooks)`, renders `<LibrarySkeleton/>` / `<ErrorState/>` / `<Empty label="Your library is empty" hint=…/>` / a `<ul>` of `<BookCard/>`. Has a section header (`"Your library"` + count). **No upload entry point** (Step 9 D2 deferred it here). Step 11 adds the entry point + modal (D1) |
| C0.2 | **`UploadResponse` schema exists** (`src/api/schemas/book.ts`) — `{book_id, status}` zod. `BookStatus` enum + `BookOut` exist. **No new schema needed** (R7.1) |
| C0.3 | **Typed client supports multipart** (`src/api/client.ts`) — `request<T>` only sets `content-type: application/json` when the body is **not** `FormData`, so multipart boundaries survive; `ApiError.friendly` already maps **413** ("That file is too large.") and **422** (passes backend `detail`). `api/books.ts` has `listBooks`/`getBook`/`ask`; `uploadBook` is added against `request` — **no client change** (R7.1) |
| C0.4 | **Primitives + cards exist** — `Button`, `Input`, `Notice`, `Empty`, `ErrorState`, `Skeleton` (`components/ui` + `components/`), `<StatusBadge status/>`, `<BookCard book/>`. Reused. **No `Dialog` primitive yet** — A3 adds one via the native `<dialog>` element |
| C0.5 | **Backend `POST /books/upload`** — multipart `file` (required; `422` if `content_type != application/pdf`), `title` (required; `422` if empty), `book_id?` (optional, Step 12); streams to `.partial`→atomic rename, **413** over `MAX_UPLOAD_MB` (default 100); **inserts + commits** the `books` row at `status='pending'` **before** returning `202 {book_id, status:"pending"}`, then schedules ingest |
| C0.6 | **`config.ts`** reads `API_BASE_URL` (`NEXT_PUBLIC_API_BASE_URL ?? "/api"`) once. A `MAX_UPLOAD_MB` constant (default 100, optional `NEXT_PUBLIC_MAX_UPLOAD_MB`) joins it for the client-side size guard (D5/A4) |

## A: Entry point + native-`<dialog>` upload modal over the library (selected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Entry point** — an "Upload book" `<Button>` on the Library: in the section header (when books exist) and as the **empty-state CTA**. Owns `open` state on `app/page.tsx` (or a small `<UploadEntry/>` wrapper) that mounts/opens `<UploadDialog/>` (D1/R1) | |
| **A2** | **`uploadBook(file, title)`** in `src/api/books.ts` — builds `FormData` (`file`, `title`), `request('/books/upload', UploadResponse, {method:'POST', body: formData})`. Reuses the `request<T>` FormData branch + existing `UploadResponse` zod; no `book_id` (D6/R2.1) | |
| **A3** | **`<UploadDialog/>`** `src/components/UploadDialog.tsx` — native `<dialog>` (`showModal()` ⇒ focus-trap + Esc + backdrop). Holds the form (A4); a `useMutation(uploadBook)`; on success → `queryClient.invalidateQueries(['books'])` + close (D2/D3/R2.2/R4.1); in-flight (disabled submit + busy) + inline error via `ApiError` message (R5.1) | |
| **A4** | **Form + client guards** — file `<input accept="application/pdf">` + title `<Input>` auto-filled from filename (D4/R3.1); on pick, validate type (reject non-PDF) + size vs `MAX_UPLOAD_MB` (D5/R3.2) with inline messages; submit disabled until valid file + non-empty title. Adds the `MAX_UPLOAD_MB` constant to `config.ts` (C0.6) | |
| **A5** | **Library reflect** — the success-path `invalidateQueries(['books'])` (A3) refetches; the committed pending row renders as `<BookCard/>` + `<StatusBadge status="pending"/>` — no optimistic/fabricated row, no polling (D2/R4.1) | |
| **A6** | **`impeccable` pass** — entry-point button(s), dialog layout + file-picker affordance + title field + submit, empty-state CTA, in-flight + inline-error states (R6.1) | |

## B: Dedicated `/upload` route (rejected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A2, A4, A5, A6 identical (same client fn, form, guards, library reflect, polish) | |
| **B2** | A new `app/upload/page.tsx` route hosts the form full-page; the Library entry point is a **`next/link`** to `/upload` (not a dialog). On success, `router.push('/')` back to the library | ⚠️ |

B avoids the dialog a11y surface, but it trades it for a **route round-trip**:
the user leaves the library to upload and is navigated back, and the "drop the new
book into the library as pending" moment (`frontend_mvp.md`) becomes a
post-navigation render rather than an in-place reveal. The native `<dialog>`
element gives A the a11y (focus-trap/Esc/backdrop) for free, so B's one advantage
mostly evaporates. The user chose the **modal** (D1): upload is a library action,
done without leaving the library. ⚠️ B2's navigate-away-and-back is the avoided
context switch.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Upload feature from the Library: modal, PDF picker + title, `POST /upload` → pending card, client guards, inline 413/422, loading, `impeccable` | Core goal | ✅ | ✅ |
| R1.1 | "Upload book" entry point on `/`, incl. as the empty-state CTA | Must-have | ✅ | ✅ |
| R2.1 | `uploadBook(file,title)` via `FormData` + `request<T>` + existing `UploadResponse`; no `book_id`; no new schema | Must-have | ✅ | ✅ |
| R2.2 | Submit via mutation; on success invalidate `['books']` + close | Must-have | ✅ | ✅ |
| R3.1 | File `<input accept=pdf>` + title auto-filled from filename, editable | Must-have | ✅ | ✅ |
| R3.2 | Client guards (reject non-PDF + oversize) before submit; submit gated | Must-have | ✅ | ✅ |
| R4.1 | `202` → pending `<BookCard/>` via refetch; no fabricated cache row | Must-have | ✅ | ✅ |
| R5.1 | In-flight + inline error (413/422 + fallback) via `ApiError` | Must-have | ✅ | ✅ |
| R6.1 | `impeccable` pass on the upload experience | Must-have | ✅ | ✅ |
| R7.1 | Reuse client/schema/cards/primitives/query; add only `uploadBook`/`MAX_UPLOAD_MB`/dialog/entry-point | Must-have | ✅ | ✅ |
| R8.1 | No re-upload / `book_id` / `failed` UX (Step 12) | Must-have | ✅ | ✅ |
| R8.2 | No live status polling | Must-have | ✅ | ✅ |
| R8.3 | No Delete; no required drag-and-drop | Must-have | ✅ | ✅ |
| R8.4 | No auth / owner-scoping | Must-have | ✅ | ✅ |

**Notes:**
- A and B both satisfy every R — they differ only on the **surface** (D1): A
  keeps the user in the library via a native-`<dialog>` modal; B navigates to a
  `/upload` route and back (⚠️ B2). The fit check is binary and both pass; the
  decision is D1's "upload is a library action, done in place," which A delivers
  without the route round-trip.

## Selected Shape

**A: Entry point + native-`<dialog>` upload modal over the library.** Decisions
baked in:

1. **Entry point** (A1/D1/R1) — "Upload book" button on `/`, also the empty-state
   CTA; opens the dialog without leaving the library.
2. **Client fn** (A2/D6/R2.1) — `uploadBook(file,title)` builds `FormData` →
   `request('/books/upload', UploadResponse, …)`; no `book_id`; no new schema.
3. **Dialog** (A3/D1/D2/D3) — native `<dialog>` (`showModal()` ⇒ focus-trap/Esc/
   backdrop); `useMutation`; on success invalidate `['books']` + close; in-flight
   + inline error.
4. **Form + guards** (A4/D4/D5) — PDF picker + title auto-filled from filename;
   reject non-PDF + oversize (`MAX_UPLOAD_MB` constant) before submit.
5. **Library reflect** (A5/D2/R4.1) — refetch shows the real committed pending
   card; no optimistic row, no polling.
6. **Polish** (A6/R6.1) — `impeccable` pass on the whole upload experience.

A's only non-trivial mechanism is the **native `<dialog>` modal + the
mutation/invalidate cycle** — ordinary client work over the existing data path,
schema, and primitives; **no flagged unknowns**.

## Out of Scope — deferred

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Re-upload by `book_id`** + **`failed` `error_message` panel + re-upload action** | New uploads only this step (D6/R8.1) | Step 12 |
| **Live status polling** (`useBookStatus`, `pending`→`ready`/`failed` in place) | Pending card is refetch-time correct; no `setInterval` (R8.2) | Step 12 |
| **Delete + confirm** | No book-removal chrome this step (R8.3) | Step 13 |
| **Drag-and-drop file zone** | A file-picker `<input>` is the affordance; drag-drop is at most an `impeccable` nicety, not a must-have (R8.3) | Optional / `impeccable` |
| **Auth / owner-scoping** | Seam reserved since Step 8 (R8.4) | Auth step (post-MVP) |

## Next Step

Breadboard Shape A (the Library entry point + `open` state, `uploadBook()`,
`<UploadDialog/>` with the native `<dialog>` + form + client guards +
mutation/invalidate, the `MAX_UPLOAD_MB` constant, and the pending-card reflect —
reusing `request<T>`/`UploadResponse`/`<BookCard/>`/`<StatusBadge/>`/primitives),
then slice. Expect a small number of vertical slices — e.g. V1 the working upload
(entry point → dialog → submit → pending card in the library, with guards +
inline errors), V2 the `impeccable` pass — each demoed against the running
backend (a real PDF uploaded, the pending card appearing in `/`).
