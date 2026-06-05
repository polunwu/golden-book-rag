---
shaping: true
---

# Step 10 · V2 — Side-by-side compare — Implementation Plan

Implements V2 of the Step 10 slices (`docs/v1/step10/slices.md`): the opt-in
"compare with plain LLM" toggle, the dual-call mutation, and the two-column
layout — built **on top of V1 without disturbing its single-column path**. No
`impeccable` pass (V3). Demoed against an API-seeded `ready` book.

Everything V2 needs already exists from V1: `ask(id, body, retrieve)` already
takes `retrieve=false` (`api/books.ts:15`), and `<AnswerView/>` already renders
**nothing** for the citation list when `citations=[]` (`Citations` returns `null`
on an empty array) and renders no refusal Notice when `refused=false`. So the
plain column is just a second `<AnswerView/>` fed the plain `AskResponse` — no new
component, no new client fn, no schema or backend change.

## What changes (and what doesn't)

The whole slice lives in **one file**: `frontend/src/components/AskPanel.tsx`.

- `<AnswerView/>` / `<Citations/>` — **unchanged**. The plain `AskResponse` has
  `refused=false` and `citations=[]`, so the same component renders a clean
  text-only column (no markers wired to anything, no Sources list).
- `api/books.ts`, `schemas/ask.ts`, the backend — **unchanged**.
- `app/books/[id]/page.tsx` — **unchanged** (still hosts `<AskPanel/>`).

## Files

| File | Change |
|------|--------|
| `frontend/src/components/AskPanel.tsx` | Add `compare` toggle state + UI (U7); make the mutation dual-call (N3′); render one or two columns from the result (U15) |

## Steps

### 1. Compare flag (U7 / S2′)

- New local state in `AskPanel`: `const [compare, setCompare] = useState(false)`.
- Render a checkbox + label between the form and the result — e.g. a `<label>`
  wrapping `<input type="checkbox" checked={compare} onChange={…} disabled={!ready || mutation.isPending} />`
  and the text "Compare with plain LLM (no retrieval)". Gate it the same as the
  input: disabled when `!ready` or `mutation.isPending`. (No `ui` toggle
  primitive exists; a plain checkbox is fine for V2 — V3 styles it.)

### 2. Dual-call mutation (N3′ / S2′)

Change the mutation so it always fires the RAG call and **additionally** fires the
plain call when `compare` is on, in parallel, and returns both:

```ts
const mutation = useMutation({
  mutationFn: async (q: string) => {
    const body = { query: q, k: 5 };
    const [rag, plain] = await Promise.all([
      ask(bookId, body, true),
      compare ? ask(bookId, body, false) : Promise.resolve(null),
    ]);
    return { rag, plain };   // plain: AskResponse | null
  },
});
```

- `compare` is read from the closure at `mutate` time (react-query keeps the
  latest `mutationFn`), so the result captures **whether compare was on for this
  ask** — toggling afterward doesn't retro-change the rendered layout.
- The result shape changes from `AskResponse` → `{ rag: AskResponse; plain: AskResponse | null }`.
  Update the `mutation.data` render (Step 3) accordingly.
- `Promise.all` → if **either** call fails the mutation rejects and the existing
  `<ErrorState/>` (U10) shows; the `409` mapping still applies to both.

### 3. One-or-two column render (U15)

Replace the single `<AnswerView .../>` block. Branch on `plain` (presence ==
compare-was-on), not on the live `compare` flag:

```tsx
{mutation.data &&
  (mutation.data.plain ? (
    <div className="mt-6 grid gap-6 md:grid-cols-2">
      <section>
        <h2 className="mb-2 font-sans text-sm font-medium text-ink-muted">With retrieval</h2>
        <AnswerView
          answer={mutation.data.rag.answer}
          refused={mutation.data.rag.refused}
          citations={mutation.data.rag.citations}
        />
      </section>
      <section>
        <h2 className="mb-2 font-sans text-sm font-medium text-ink-muted">Without retrieval</h2>
        <AnswerView
          answer={mutation.data.plain.answer}
          refused={mutation.data.plain.refused}
          citations={mutation.data.plain.citations}
        />
      </section>
    </div>
  ) : (
    <AnswerView
      answer={mutation.data.rag.answer}
      refused={mutation.data.rag.refused}
      citations={mutation.data.rag.citations}
    />
  ))}
```

- **Single-column path is byte-for-byte the V1 render** (one `<AnswerView/>` fed
  the RAG response) — V1's demo is untouched.
- `<AnswerView/>` carries its own `mt-6`; inside a column with an `<h2>` heading
  that doubles the top gap. Acceptable for V2 (functional); V3 owns the grid +
  column-header polish. Don't refactor `<AnswerView/>`'s spacing now.
- Two-column on `md:` and up; stacks to one column on narrow by default. Final
  responsive behavior is V3's, but the `grid` already collapses gracefully.

## Styling (V2 = functional; polish is V3)

Plain checkbox + muted column headers using existing tokens (`text-ink-muted`,
`font-sans`). No new visual system. V3 (`impeccable`) owns the compare grid,
column dividers/headers, responsive collapse, and toggle styling.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; seed a book to `ready`;
`make web`; open `/books/{id}`:

1. **Compare off (default)** → ask → single column, identical to V1 (grounded
   answer + `[n]` markers + Sources). Confirm **one** `/ask` request in the
   Network tab.
2. **Compare on** → ask → two columns: left "With retrieval" (answer + markers +
   citations), right "Without retrieval" (plain answer, no markers wired, no
   Sources, `refused=false`). Confirm **two** `/ask` requests (one with, one
   without `?retrieve=false`), fired in parallel.
3. Toggle on, ask, then toggle **off** without re-asking → the rendered result
   stays two-column (reflects the ask that produced it); the next ask with the
   toggle off renders single-column.
4. Marker click in the left column still scrolls/highlights its own Sources
   (refs are scoped per `<AnswerView/>`, so the two columns don't collide).
5. Gate (non-`ready` book): input, Ask button, **and** the compare checkbox all
   disabled with the gate notice (U11).
6. Stop the API mid-ask with compare on → `Promise.all` rejects → single
   `<ErrorState/>` (U10).
7. `yarn lint` / typecheck clean.

## Out of V2 (later slices)

- **`impeccable` pass** — compare-grid layout, column headers/dividers,
  responsive collapse, toggle + marker + citation-card polish, refusal/loading
  states → V3.
- Streaming, caching the plain answer across re-asks, per-column loading
  skeletons, `k`-UI → out of Step 10 (shaping R8).
