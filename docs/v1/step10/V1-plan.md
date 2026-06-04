---
shaping: true
---

# Step 10 · V1 — Single-answer Ask — Implementation Plan

Implements V1 of the Step 10 slices (`docs/v1/step10/slices.md`): the real book
page + the core ask loop with **one** call (`retrieve=true`). No compare toggle
(V2), no `impeccable` pass (V3). Demoed against an API-seeded `ready` book.

Reuses, unchanged: the typed client `request<T>` + `ApiError` (`src/api/client.ts`),
the `ask.ts`/`book.ts` zod schemas, `<StatusBadge/>`, `<ErrorState/>`, the
`formatDate`/`bookTitle` helpers, and the Library's inline-skeleton + `ErrorState`
loading/error pattern (there is **no** `<Loading/>` component — match
`app/page.tsx`'s `LibrarySkeleton` idiom).

> ⚠️ **Next 16, not the Next.js you know** (`frontend/AGENTS.md`). Before writing
> the route component, check `node_modules/next/dist/docs/` for the current App
> Router client-component + `params` conventions. The existing placeholder uses
> `params: Promise<{id}>` in a **server** component; V1 makes the page a
> **client** component (`"use client"`) — confirm how a client page reads route
> params in this version (e.g. `use(params)` / `useParams()`), don't assume.

## Files

| File | Change |
|------|--------|
| `frontend/src/api/books.ts` | **Add** `getBook(id)` and `ask(id, body, retrieve)`; export `AskResponse`/`Citation` types |
| `frontend/src/lib/format.ts` | **Add** `pageRange(page_start, page_end)` and `breadcrumb(section_path)` helpers |
| `frontend/src/app/books/[id]/page.tsx` | **Replace** placeholder → `"use client"` book page: `useQuery(['book',id])`, header (back-link + title + `<StatusBadge/>`), hosts `<AskPanel/>` |
| `frontend/src/components/AskPanel.tsx` | **New** — input + gated Ask button + mutation + loading/error/gate states; renders `<AnswerView/>` |
| `frontend/src/components/AnswerView.tsx` | **New** — answer text w/ parsed clickable `[n]` markers + refusal signal; renders `<Citations/>` |
| `frontend/src/components/Citations.tsx` | **New** — full always-visible citation list; each item is a scroll/highlight target |

No schema changes (R7.1) — `AskResponse`, `Citation`, `BookOut` already exist.

## Steps

### 1. Client functions (`api/books.ts`) — N2, N4

```ts
import { request } from "./client";
import { BookOut } from "./schemas/book";
import { AskResponse, type AskRequest } from "./schemas/ask";

export async function getBook(id: string): Promise<BookOut> {
  return request(`/books/${id}`, BookOut);
}

export async function ask(
  id: string,
  body: AskRequest,            // { query, k }
  retrieve: boolean,
): Promise<AskResponse> {
  const path = `/books/${id}/ask${retrieve ? "" : "?retrieve=false"}`;
  return request(path, AskResponse, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type { BookOut, AskResponse, Citation } from … ;
```

- `request` already sets `content-type: application/json` for a non-FormData body
  (`client.ts:44-50`) and zod-parses `AskResponse`; `409`/`404` map to friendly
  `ApiError.message` (`409` → "This book isn't ready yet.").
- `id` goes straight into the path. It is a backend-issued uuid string from the
  route; no interpolation of user free-text into the path.

### 2. Format helpers (`lib/format.ts`) — N7

```ts
export function pageRange(start: number | null, end: number | null): string | null {
  if (start == null && end == null) return null;
  if (start != null && end != null && start !== end) return `pp. ${start}–${end}`;
  return `p. ${start ?? end}`;
}

export function breadcrumb(section_path: string[] | null): string | null {
  return section_path?.length ? section_path.join(" › ") : null;
}
```

### 3. Book page (`app/books/[id]/page.tsx`) — A1, N1, U1–U5

- `"use client"`; read `id` from route params per the **Next 16** convention
  (verify in the docs — see warning above).
- `useQuery({ queryKey: ['book', id], queryFn: () => getBook(id) })` (S1).
- Render:
  - **loading** → inline skeleton (header bar + input placeholder), matching
    `LibrarySkeleton` idiom (U1).
  - **error** → `<ErrorState detail={(error as Error).message} />` (covers `404`
    "Not found.", backend down) (U2).
  - **data** → header: a "← Library" `<Link href="/">` (U5), `bookTitle(book)`
    (U3), `<StatusBadge status={book.status} />` (U4); then
    `<AskPanel bookId={id} status={book.status} />`.

### 4. `<AskPanel/>` (`components/AskPanel.tsx`) — A3, U6, U8–U11, N3 (single)

- Local state: `query` (controlled input).
- `const ready = status === "ready"`.
- `useMutation({ mutationFn: (q: string) => ask(bookId, { query: q, k: 5 }, true) })`
  (N3, single call; S2). `k:5` hardcoded (D5).
- **Gate** (D6/R1.2): if `!ready`, render a gate notice (U11) — e.g. a muted
  panel "This book is **{status}** — ask is available once it's ready." and the
  input + Ask button **disabled**. Belt-and-braces with the backend `409`.
- Submit (form `onSubmit`/Ask button, U6/U8): disabled when `!ready` or
  `query.trim()` empty or `mutation.isPending`; on submit → `mutation.mutate(query.trim())`.
- States: `isPending` → loading affordance (U9, e.g. button "Asking…" +
  disabled); `error` → `<ErrorState detail={(error as Error).message} />` (U10,
  surfaces `409` if the gate was bypassed by a race).
- On success → `<AnswerView answer={data.answer} refused={data.refused} citations={data.citations} />`.

### 5. `<AnswerView/>` (`components/AnswerView.tsx`) — A4, A6, U12–U14, N5, N6

- **Marker parse (N5)**: split `answer` on `/\[(\d+)\]/g`, keeping the captured
  numbers; render text runs as-is and each `[n]` as a `<button>` (U13). Map `n` to
  the citation whose `marker === n`; if no match, render the `[n]` as inert text
  (don't crash on a marker without a citation).
- **Scroll + highlight (N6)**: hold a `Map<number, HTMLElement>` via callback
  refs registered by `<Citations/>` items (or query by `id={`cite-${marker}`}`).
  On marker click → `el.scrollIntoView({ behavior: 'smooth', block: 'center' })`
  + add a transient highlight class (e.g. set a `highlighted` marker in state,
  clear after ~1.2s via `setTimeout`).
- **Refusal (R3.2/U14)**: when `refused`, render the answer text **and** a clear
  refusal signal (a labeled notice, e.g. "Not enough in this book to answer
  confidently"); citations are `[]` so `<Citations/>` renders nothing.
- Render `<Citations citations={citations} highlighted={highlighted} registerRef={…} />`.

### 6. `<Citations/>` (`components/Citations.tsx`) — A5, U16

- Return `null` if `citations.length === 0`.
- Heading "Sources"; ordered list, each item (D3 — **full, always visible, no
  expand/hover**):
  - id/anchor `id={`cite-${c.marker}`}` (+ ref registration) so N6 can target it.
  - `[{c.marker}]` lead.
  - `breadcrumb(c.section_path)` (N7) if present.
  - `pageRange(c.page_start, c.page_end)` (N7) if present.
  - `score` formatted (e.g. `c.score.toFixed(2)`).
  - the **full** `c.text` (readable block, no truncation/expander).
  - highlight class when `highlighted === c.marker`.

## Styling (V1 = functional; polish is V3)

Plain but coherent with existing tokens (`text-ink`, `text-ink-muted`,
`bg-paper-raised`, `border-rule`, `bg-status-*`). V1 aims for correct structure
and legible defaults; V3 owns hierarchy/typography/responsive polish.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; seed a book and let it reach
`ready`; `make web`; then:

1. `/` → click a card → `/books/{id}` shows back-link, title, `Ready` badge.
2. Ask a question answerable from the book → grounded answer with inline `[1]…`
   markers + a "Sources" list (breadcrumb, page range, score, full text).
3. Click a `[n]` marker → page scrolls to + briefly highlights citation `n`.
4. Ask an off-topic question → refusal signal shown with the answer text, no
   citations.
5. Open a `pending`/`processing` book → input + Ask disabled, gate notice shown.
6. Stop the API mid-ask (or before) → ask error state via `ApiError`.
7. `yarn lint`/typecheck clean.

## Out of V1 (later slices)

- **Compare toggle + dual call + 2-column layout** → V2.
- **`impeccable` pass** (typography, marker styling, compare grid responsive,
  citation-card polish) → V3.
- Count/Delete/Upload/polling/auth/`k`-UI/expandable-citations → out of Step 10
  entirely (shaping R8).
