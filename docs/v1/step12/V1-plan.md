---
shaping: true
---

# Step 12 · V1 — Live library polling — Implementation Plan

Implements V1 of the Step 12 slices (`docs/v1/step12/slices.md`): the shared
polling policy + its single consumer, so library badges flip
`pending→processing→ready/failed` **live with no manual refresh** (closing Step
11's deferred R8.2), and polling **self-stops** once every card is terminal.
**No** book-page panels / re-upload / `book_id` (V2), **no** `impeccable` pass
(V3). Demoed against the running backend with a real PDF.

This is the smallest slice in the step: one new pure-helper module + one
`refetchInterval` line. No new UI — `<BookCard/>`/`<StatusBadge/>` already render
every status, so badges flip in place as the poll returns fresh rows.

Reuses, unchanged: the `['books']` `useQuery` on `app/page.tsx`, `listBooks()` →
`GET /books`, `<BookCard/>` + `<StatusBadge/>` (all four states, `processing`
already pings), the `BookOut`/`BookStatus` zod, and the backend ingest that drives
`books.status` (watched via the poll). **No backend work** (R7.1).

> ⚠️ **Next 16, not the Next.js you know** (`frontend/AGENTS.md`). V1 touches only
> client-component surface (`app/page.tsx` is already `"use client"`) + a plain TS
> helper. No routing/`params`/server-component changes. `refetchInterval` is
> TanStack Query, not Next — no Next API involved.

## Files

| File | Change |
|------|--------|
| `frontend/src/lib/status.ts` | **New** — `isTerminal(status)` + `refetchIntervalFor(books, ms?)` (the shared stop-rule policy, A1/N1) |
| `frontend/src/app/page.tsx` | **Add** `refetchInterval` to the existing `['books']` `useQuery`, fed by `refetchIntervalFor` (A2/N2) |

No schema, no client, no component changes. `BookStatus` is already exported from
`src/api/schemas/book.ts`; `BookOut[]` is the `['books']` query's data type.

## Steps

### 1. Shared polling policy (`lib/status.ts`) — A1/N1

New pure module (no React, no imports beyond the `BookStatus`/`BookOut` types) so
it is trivially testable and has one job: own the **stop rule** (D4/R1.1).

```ts
import type { BookOut, BookStatus } from "@/api/schemas/book";

// Terminal = ingest is done (succeeded or failed) — no further status change is
// coming, so there is nothing left to poll for.
const TERMINAL: ReadonlySet<BookStatus> = new Set(["ready", "failed"]);

export function isTerminal(status: BookStatus): boolean {
  return TERMINAL.has(status);
}

// The single source of the "when to poll / when to stop" rule (D4). Poll while
// ANY observed book is still non-terminal; stop (false) once every book is
// terminal — or when there are no books to watch. Fed to the ['books']
// useQuery's refetchInterval; no setInterval/useEffect timer anywhere (R1.4).
export function refetchIntervalFor(
  books: BookOut[] | undefined,
  ms = 2000,
): number | false {
  if (!books?.length) return false;
  return books.some((b) => !isTerminal(b.status)) ? ms : false;
}
```

- **`false` is the stop** — TanStack Query treats `refetchInterval: false` as "no
  interval", so the cross-cutting "stop polling at terminal states" is literally a
  `return false`; no manual timer teardown (R1.4).
- **Empty / undefined → `false`** — an empty library (or the pre-first-fetch
  `undefined`) has nothing non-terminal to watch, so don't spin a timer; the
  initial fetch still happens (that's `queryFn`, not the interval).
- **`ms` is a parameter** (default 2000) so V2/tests can pass a different cadence
  without touching the rule. Ingest runs in seconds–minutes, so ~2s is responsive
  without hammering the backend.

### 2. Library consumer (`app/page.tsx`) — A2/N2/U2

The **only** polling call site (D1). Add `refetchInterval` to the existing query:

```tsx
import { refetchIntervalFor } from "@/lib/status";
// …
const { data, isLoading, error } = useQuery({
  queryKey: ["books"],
  queryFn: listBooks,
  refetchInterval: (query) => refetchIntervalFor(query.state.data),
});
```

- **Function form** — TanStack Query v5 passes the `Query` to a `refetchInterval`
  function; `query.state.data` is the current `BookOut[]`. Re-evaluated after each
  fetch, so as the last non-terminal card flips to `ready`/`failed` the next return
  is `false` and the loop ends on its own.
- **No other change** — the loading/error/empty/list branches, `<BookCard/>`, and
  the badge are untouched. A returned row's new `status` flows through the existing
  render, so the badge flips in place (the live transition U2).
- **Background tabs** — TanStack's default `refetchIntervalInBackground: false`
  pauses the poll on a blurred tab and resumes on focus; acceptable for the MVP
  (and the focus refetch catches up immediately). Not overridden in V1.

> The book page (`app/books/[id]/page.tsx`) is **not touched** in V1 — it stays an
> un-polled reader (D1/R1.3); its processing/failed panels are V2. The shared
> `isTerminal` helper will be reused by V2's panel pick, but V1 only needs the
> policy + the library consumer.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; `make web`; then:

1. Open `/`. Upload a real PDF (the Step 11 dialog) → a **`Pending`** card appears.
2. **Without refreshing**, watch the badge flip **`Pending → Processing`** (the
   ping animates) **→ `Ready`** as the backend ingest progresses.
3. Confirm the poll **self-stops**: with React Query devtools (or the network/API
   request log), the `['books']` query refetches ~every 2s **only while** a card is
   non-terminal, and **stops** once all cards are `ready`/`failed`. Reloading an
   all-terminal library issues a single fetch and no interval.
4. (Optional) force a `failed` row in `make db-shell` (`UPDATE books SET status='failed'`)
   while another book is still processing → the failed badge appears live and the
   poll keeps running until the *other* book also terminates.
5. `yarn lint` + typecheck clean.

## Out of V1 (later slices)

- **Book-page processing panel** (`pending`/`processing`), **failed panel**
  (read-only `error_message`), the **`failed` library card's Re-upload**
  affordance, **`uploadBook(file, title, bookId?)`**, the **dialog re-upload mode**,
  and the **richer `{open, bookId?, title?}` upload state** → V2.
- **`impeccable` pass** (panels, failed-card affordance, smooth transitions) → V3.
- **Websockets/SSE**, **Delete**, **auth** → out of Step 12 (shaping R7).
