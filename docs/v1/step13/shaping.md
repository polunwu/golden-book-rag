---
shaping: true
---

# Step 13: Delete — book-page delete + confirm dialog — Shaping

Step 9 shipped the **Library**, Step 10 the **Ask** panel, Step 11 the **Upload**
modal, Step 12 the **Status** feature (live polling, processing/failed panels,
failed-card re-upload). Step 12's Out of Scope punted book removal to here:
"**Delete + confirm** — no book-removal chrome this step (R7.3) → Step 13." Step 13
closes the last MVP screen affordance with the **Delete** feature.

Carried in from `frontend_mvp.md` (verbatim drivers):

- Step 13 = `Delete   delete book + confirm`.
- Screen 2 Book page: "Header: title, status, page/chunk count, **delete**".
- Screen 1 Library card: "Each card: title, status badge, created date,
  ask/**delete** actions". *(Step 13 deliberately does not add a card delete — D1;
  see Settled decisions.)*
- Backend contract: `DELETE /books/{id}` → `204`; "**also deletes the PDF**".
- "Each gets its own shape-up + `impeccable` pass."

**Step 13 is FE-only.** The backend already exists: `DELETE /books/{id}`
(`api/routers/books.py:233`) deletes the `books` row (cascades `chunks` →
`chunk_embeddings`), unlinks the PDF (`file_path.unlink(missing_ok=True)`),
returns `404` if unknown, `204` on success. No migration, no router change.

## Settled decisions (pre-shape forks)

Resolved with the user at shaping kickoff (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Delete entry point** | **Book-page header only — *not* the library card.** Delete lives solely in the book-page header; the `<BookCard/>` is unchanged. This **diverges from `frontend_mvp.md`** ("card: ask/delete actions") — an intentional simplification: the card just gained the failed-card Re-upload affordance in Step 12, and a second (destructive) action crowds the row and risks mis-clicks in a scannable list. Delete belongs where the user is focused on a single book, and **delete-then-navigate-to-library is a clean flow** (unlike Step 12's re-upload, which was kept library-only — D2 there — precisely because a book-page re-upload would strand the user on the non-polling `pending` view; delete has no such wrinkle — it leaves the page entirely). (Considered: both card + header per the driver — rejected by the user; card-only — rejected.) |
| D2 | **Confirm mechanism** | **A reusable `<ConfirmDialog>` in `components/ui/`.** Native `<dialog>` element, styled and accessible, following the **same mechanism split as `BookUploadDialog`**: the **container** (book page) owns the *mechanism* (`useMutation` + cache update + navigation); the `<ConfirmDialog>` is **presentational** (`open` / `onConfirm` / `onCancel` + title/body/labels). It is generic and cross-resource, so it lives in `ui/` and is re-exported from the barrel (per the ui-barrel convention). (Considered: native `window.confirm()` — rejected: unstyleable, off-brand, hard to test, clashes with the Step 9–12 `impeccable` ethos; inline two-step morph — rejected: bespoke per call site, awkward to share.) |
| D3 | **Cache + navigation on success** | **Optimistic removal + rollback.** On confirm, the mutation **optimistically removes** the book from the `['books']` list cache (and drops the `['book', id]` entry), then `router.push('/')` to the library — which already shows the book gone (no flash, no refetch wait). **On error, roll back** the `['books']` cache, keep the user on the book page, and surface the failure. (Considered: plain `invalidateQueries(['books'])` — rejected by the user: consistent with the upload path but a beat slower; optimistic suits a destructive action that navigates away.) |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A **Delete** feature: the **book-page header** exposes a Delete action (the sole entry — D1) that opens a **reusable `<ConfirmDialog>`** (ui/, D2); confirming fires `DELETE /books/{id}`, **optimistically removes** the book from the library cache and **navigates back to the library** (D3), and **rolls back + surfaces an error** on failure; the library card is unchanged; finished with an `impeccable` pass | Core goal |
| **R1** | **Delete entry (book page)** | Must-have |
| R1.1 | The **book-page header** gains a **Delete** affordance — the **sole** delete entry (D1). Available for **any** status (you especially want to remove a `failed` book). The `<BookCard/>` / library row is **not** changed | Must-have |
| **R2** | **Confirm dialog** | Must-have |
| R2.1 | A **reusable `<ConfirmDialog>`** under `components/ui/` (barrel-exported): native `<dialog>`, **destructive framing** (the book's title, an "irreversible — also deletes the PDF and all chunks" warning, a danger-styled **Delete** + a **Cancel**), accessible (focus on open, Escape, backdrop click → cancel) (D2) | Must-have |
| R2.2 | **Mechanism/presentation split** (mirrors `BookUploadDialog`): the **container** owns `useMutation` + the cache update + navigation; the dialog takes `open` / `onConfirm` / `onCancel` + copy props and renders nothing else. Generic ⇒ lives in `ui/`, not `books/` (D2) | Must-have |
| **R3** | **Delete request** | Must-have |
| R3.1 | `deleteBook(id)` in `api/books.ts` → `request('/books/{id}', z.void(), { method: 'DELETE' })`. The wrapper **already handles `204`** (parses against the passed schema; `z.void()` for no-content) and maps `404`/errors via `ApiError`. No client-wrapper change | Must-have |
| **R4** | **Cache + navigation** | Must-have |
| R4.1 | **Optimistic success**: on confirm, `onMutate` removes the book from the `['books']` cache and drops `['book', id]`; on `204`, `router.push('/')` — the library renders without the book, no refetch wait (D3) | Must-have |
| R4.2 | **Rollback on error**: `onError` restores the snapshotted `['books']` cache, keeps the user on the book page, and surfaces the failure (a `<Notice/>`/error affordance); the dialog reflects the busy/error state while the mutation runs (D3) | Must-have |
| **R5** | **Reuse the existing seams** | Must-have |
| R5.1 | Reuse the typed `request` wrapper (incl. its `204` path), the native-`<dialog>` pattern from `BookUploadDialog`, TanStack `useMutation`, `Button` (a danger variant), and the `['books']`/`['book', id]` queries. **Add only**: `deleteBook(id)`, the `<ConfirmDialog>` (+ barrel export), the book-page Delete button, and its mutation wiring (optimistic remove + rollback + navigate) | Must-have |
| **R6** | **Polish** | Must-have |
| R6.1 | An **`impeccable` pass**: the header Delete affordance (placement next to the badge, danger styling restrained until confirm), the confirm dialog (destructive copy, motion, focus), and the post-delete transition to the library | Must-have |
| **R7** | **Scope boundaries** | Must-have |
| R7.1 | **No backend work** — `DELETE /books/{id}` (cascade + PDF unlink + `204`/`404`) already exists; Step 13 is FE-only | Must-have |
| R7.2 | **No library-card delete** (D1); **no bulk delete**; **no undo toast / soft-delete** — optimistic rollback covers the *error* case, not a post-success undo (delete is permanent, the confirm dialog is the guard) | Must-have |
| R7.3 | **No auth / owner-scoping** — seam reserved since Step 8 | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **Book page** `app/books/[id]/page.tsx` — `useQuery(['book', id], getBook)` (un-polled, fresh on mount); header = `<h1>{title}</h1>` + `<StatusBadge>`; body picks `<AskPanel/>` (`ready`) / `<FailedPanel/>` (`failed`) / `<ProcessingPanel/>` (else) by status; has the `← Library` link. **A pure status reader — no mutation** (Step 12 D1/D2). Step 13 adds the header **Delete** button + the `<ConfirmDialog/>` + the delete `useMutation` (A3/A4) |
| C0.2 | **Library page** `app/page.tsx` — `useQuery(['books'], listBooks)` with `refetchInterval` (Step 12 V1); renders `<BookCard/>`s; owns the upload modal state. Step 13's optimistic delete **writes this cache** (removes the deleted row via `onMutate`) and is the `router.push('/')` destination, but adds **no card UI** (D1) |
| C0.3 | **`BookUploadDialog`/`BookUploadForm`** (`components/books/`) — native `<dialog>`, `useMutation` + `onSuccess → invalidateQueries` + close; container owns mechanism, form is presentational. **The model for `<ConfirmDialog>`'s mechanism/presentation split** (D2/R2.2). Not modified |
| C0.4 | **`api/books.ts`** — `listBooks`/`getBook`/`ask`/`uploadBook`; **no `deleteBook`**. Step 13 adds `deleteBook(id)` (A1) |
| C0.5 | **`request<T>` wrapper** (`api/client.ts`) — throws `ApiError` on non-2xx; **already special-cases `204`** ("204 No Content (e.g. DELETE) has no body … validate against the caller's schema (pass `z.void()`)"). `ApiError.friendly` maps `404`. **No change** (R3.1/R5.1) |
| C0.6 | **`components/ui/`** — `Button`/`Input`/`Notice`/`Empty`/`ErrorState`/`FieldError`/`Skeleton`, barrel-exported from `ui/index.ts`. **No `ConfirmDialog` yet.** Step 13 adds `<ConfirmDialog>` here + the barrel line (A2); `Button` gains a danger variant if not present (A2) |
| C0.7 | **Backend** — `DELETE /books/{id}` (`api/routers/books.py:233`): `DELETE … RETURNING file_path`; `404` if no row; else commit, `unlink(missing_ok=True)` the PDF, `204`. `books → chunks → chunk_embeddings` cascade on the row delete. **All present** (R7.1) |

## A: Book-page Delete + reusable ConfirmDialog + optimistic mutation (selected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **`deleteBook(id)`** — `api/books.ts`: `request(\`/books/${id}\`, z.void(), { method: 'DELETE' })`; relies on the wrapper's existing `204` path + `404` mapping (D3/R3.1) | |
| **A2** | **Reusable `<ConfirmDialog>`** — `components/ui/ConfirmDialog.tsx` (+ barrel export): native `<dialog>` synced to an `open` prop, props `title`/`body`/`confirmLabel`/`cancelLabel`/`destructive`/`busy` + `onConfirm`/`onCancel`; danger-styled confirm `Button`, Escape/backdrop → cancel, focus management. Presentational only (R2.1/R2.2/D2) | |
| **A3** | **Book-page Delete affordance** — `app/books/[id]/page.tsx` header gains a Delete button (next to `<StatusBadge>`), shown for any status (D1/R1.1); opens the `<ConfirmDialog>` seeded with the book's title | |
| **A4** | **Delete mutation (optimistic + rollback + navigate)** — `useMutation(() => deleteBook(id))`: `onMutate` snapshots + removes the book from `['books']` and drops `['book', id]`; `onSuccess` `router.push('/')`; `onError` restores the snapshot, stays on the page, surfaces the error; the dialog shows `busy` while pending (D3/R4.1/R4.2) | |
| **A5** | **`impeccable` pass** — header Delete placement + restrained danger styling, the confirm dialog's destructive copy/motion/focus, and the post-delete transition to the library (R6.1) | |

A's only non-trivial mechanism is the **optimistic `['books']` cache edit + rollback**
(ordinary TanStack `onMutate`/`onError` over the existing query); the `<dialog>`
pattern, the `204` client path, the `Button`, and the queries all exist. **No
flagged unknowns.**

## B: Native `window.confirm()` + invalidate (rejected)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A1 identical (`deleteBook(id)`) | |
| **B2** | Book-page header Delete button calls `window.confirm('Delete …?')`; on OK, `mutate`. **No reusable dialog component** | |
| **B3** | `onSuccess`: `invalidateQueries(['books'])` + `router.push('/')`. No optimistic edit, no rollback | ⚠️ |

B trades the styled, testable, reusable confirm for the browser's unstyleable
native prompt (off-brand vs every Step 9–12 surface, awkward to test), and the
snappy optimistic navigate for an invalidate-then-refetch beat. The user chose the
reusable dialog (D2) and optimistic removal (D3). ⚠️ B3's invalidate-without-snapshot
gives up the rollback path R4.2 needs.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Delete feature: book-page Delete → reusable confirm → DELETE, optimistic remove + navigate, rollback on error, card unchanged, `impeccable` | Core goal | ✅ | ❌ |
| R1.1 | Book-page header Delete (sole entry, any status); card unchanged | Must-have | ✅ | ✅ |
| R2.1 | Reusable `<ConfirmDialog>` (ui/): destructive framing, accessible | Must-have | ✅ | ❌ |
| R2.2 | Mechanism/presentation split (container owns mutation; dialog presentational) | Must-have | ✅ | ❌ |
| R3.1 | `deleteBook(id)` via the `204`-aware `request` wrapper; `404` mapped | Must-have | ✅ | ✅ |
| R4.1 | Optimistic removal from `['books']` + navigate to library | Must-have | ✅ | ❌ |
| R4.2 | Rollback on error; stay on page; surface failure | Must-have | ✅ | ❌ |
| R5.1 | Reuse wrapper/dialog pattern/mutation/Button/queries; add only the listed pieces | Must-have | ✅ | ✅ |
| R6.1 | `impeccable` pass | Must-have | ✅ | ✅ |
| R7.1 | No backend work (FE-only) | Must-have | ✅ | ✅ |
| R7.2 | No card delete / bulk / undo-toast | Must-have | ✅ | ✅ |
| R7.3 | No auth / owner-scoping | Must-have | ✅ | ✅ |

**Notes:**
- B fails R2.1/R2.2: `window.confirm()` is not a styled, accessible, reusable
  component and has no mechanism/presentation split.
- B fails R4.1/R4.2: invalidate-without-snapshot gives no optimistic removal and
  no rollback path. These cascade to R0.
- A and B share the request (A1≡B1) and the header entry (R1.1); they differ on
  the confirm mechanism (D2) and the cache strategy (D3), which decide the fit.

## Selected Shape

**A: Book-page Delete + reusable `ConfirmDialog` + optimistic mutation.**
Decisions baked in:

1. **`deleteBook(id)`** (A1/D3/R3.1) — `DELETE /books/{id}` via the `204`-aware
   `request` wrapper (`z.void()`).
2. **Reusable `<ConfirmDialog>`** (A2/D2/R2.1/R2.2) — native `<dialog>` in `ui/`,
   presentational, destructive framing; container owns the mechanism.
3. **Book-page Delete affordance** (A3/D1/R1.1) — header button (sole entry, any
   status); the library card is untouched.
4. **Optimistic mutation** (A4/D3/R4.1/R4.2) — `onMutate` removes from `['books']`
   + drops `['book', id]`; `onSuccess` navigates to `/`; `onError` rolls back and
   surfaces the failure.
5. **Polish** (A5/R6.1) — `impeccable` pass on the header affordance, the dialog,
   and the post-delete transition.

## Out of Scope — deferred

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Library-card delete** | Driver names it, but a second destructive action crowds the scannable row and risks mis-clicks; Delete lives on the book page (D1) | Out (MVP) — could revisit if a list-level bulk action is ever wanted |
| **Undo toast / soft-delete** | Delete is permanent; the confirm dialog is the guard. Optimistic rollback handles the *error* path, not a post-success undo (R7.2) | Out (MVP) |
| **Bulk delete / multi-select** | No list-selection chrome in the MVP (R7.2) | Out (MVP) |
| **Deleting mid-ingest (race)** | Pure backend concern: the row is gone; a still-running `run_ingest` writes status on a fresh connection that no-ops/errors against the deleted row. Not an FE matter | Out (backend, if ever) |
| **Per-book page/chunk counts in the header** (`frontend_mvp.md` screen 2) | Orthogonal header content, not a delete concern (also noted in Step 12) | Optional / later |
| **Auth / owner-scoping** | Seam reserved since Step 8 (R7.3) | Auth step (post-MVP) |

## Next Step

Breadboard Shape A (`deleteBook(id)`; the `<ConfirmDialog>` in `ui/` + barrel
export; the book-page header Delete button; the optimistic delete `useMutation`
with `onMutate` snapshot/remove, `onSuccess` `router.push('/')`, `onError`
rollback — reusing the `204`-aware `request` wrapper, the `BookUploadDialog`
`<dialog>` pattern, `Button`, and the `['books']`/`['book', id]` queries), then
slice. Expect a small number of vertical slices — e.g. V1 the delete request +
reusable `<ConfirmDialog>` + book-page Delete wired with optimistic removal and
navigation (the whole feature, demo-able: open a book → Delete → confirm → land
in the library with the book gone), V2 the `impeccable` pass — each demoed against
the running backend (upload a real PDF, open it, delete it, confirm it's gone from
the library *and* the PDF is unlinked on disk). This is the **last MVP screen
affordance** — after Step 13 the FE success criteria are met end to end.
