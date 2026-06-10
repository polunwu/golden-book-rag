---
shaping: true
---

# Step 11 · V1 — Working upload (happy path) — Implementation Plan

Implements V1 of the Step 11 slices (`docs/v1/step11/slices.md`): the upload entry
point + the core loop — open the dialog, pick a PDF (title auto-fills), submit,
and on `202` the real committed **pending** card appears in `/` via an `['books']`
refetch. **No** client guards / server-error surface / busy state / explicit
Cancel affordance (V2), **no** `impeccable` pass (V3). Demoed against the running
backend with a real PDF.

Reuses, unchanged: the typed client `request<T>` + `ApiError` (`src/api/client.ts`,
whose FormData branch already keeps the multipart content-type), the
`UploadResponse` zod (`src/api/schemas/book.ts`), `<BookCard/>` + `<StatusBadge/>`,
the `['books']` `useQuery` on `app/page.tsx`, and the `Button`/`Input` primitives.

> ⚠️ **Next 16, not the Next.js you know** (`frontend/AGENTS.md`). V1 touches only
> client-component surface (`app/page.tsx` is already `"use client"`; the dialog
> is a client component over the **browser-native `<dialog>`** element, not a Next
> API). No routing/`params`/server-component changes. If anything Next-specific
> creeps in, check `node_modules/next/dist/docs/` first — don't assume.

## Files

| File | Change |
|------|--------|
| `frontend/src/api/books.ts` | **Add** `uploadBook(file, title)`; export the `UploadResponse` type |
| `frontend/src/components/UploadDialog.tsx` | **New** — native `<dialog>` modal: file picker + auto-filled title + submit; `useMutation(uploadBook)`; on success invalidate `['books']` + close |
| `frontend/src/app/page.tsx` | **Add** `open` state, a header "Upload book" `<Button>`, the empty-state CTA, and `<UploadDialog/>` |
| `frontend/src/components/Empty.tsx` | **Add** an optional `action` slot (the empty-state CTA renders through it) |

No schema changes (R7.1) — `UploadResponse` already exists. No client change —
`request<T>` already handles `FormData`.

## Steps

### 1. Client function (`api/books.ts`) — N6

```ts
import { request } from "./client";
import { BookList, BookOut, UploadResponse } from "./schemas/book";
// …existing listBooks / getBook / ask…

export async function uploadBook(
  file: File,
  title: string,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  return request("/books/upload", UploadResponse, {
    method: "POST",
    body: form,
  });
}

export type { UploadResponse } from "./schemas/book";
```

- `request` leaves the `content-type` unset for a `FormData` body (`client.ts:44-50`),
  so the browser sets `multipart/form-data; boundary=…` itself — the boundary
  survives (C0.3).
- The backend reads `file` + `title` from the multipart form; V1 never sends
  `book_id` (D6 — new uploads only).
- `202` is `res.ok`, parsed against `UploadResponse` (`{book_id, status}`); a
  `413`/`422` becomes a friendly `ApiError` (surfaced in V2, not V1).

### 2. `<Empty/>` action slot (`components/Empty.tsx`) — supports U2

Add an optional `action?: React.ReactNode` rendered under the hint:

```tsx
export function Empty({ label = "Nothing here yet.", hint, action }: {
  label?: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="py-20 text-center">
      <p className="text-lg text-ink">{label}</p>
      {hint && <p className="mt-1.5 font-sans text-sm text-ink-muted">{hint}</p>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}
```

Keeps `<Empty/>` reusable; the Library passes the same "Upload book" button as
its CTA (other callers omit `action`).

### 3. `<UploadDialog/>` (`components/UploadDialog.tsx`) — A3/A4 (core), U4, U5, U7, N3 (autofill), N5, N6, N7

`"use client"`. Props: `{ open: boolean; onClose: () => void }`.

- **Native `<dialog>` sync** — `const ref = useRef<HTMLDialogElement>(null)`;
  `useEffect(() => { const d = ref.current; if (!d) return; if (open && !d.open) d.showModal(); else if (!open && d.open) d.close(); }, [open])`.
  Render `<dialog ref={ref} onClose={onClose} …>` so the **native close event**
  (Esc) syncs React state back via `onClose` — Esc shouldn't desync `open`. (The
  styled Cancel button + backdrop-click-to-close are V2.)
- **Local state** — `const [file, setFile] = useState<File | null>(null)`;
  `const [title, setTitle] = useState("")`.
- **File pick (N3, autofill only)** — on the file `<input>`'s `onChange`, take
  `e.target.files?.[0] ?? null`; `setFile(f)`; if `f`, `setTitle(stripPdf(f.name))`
  where `stripPdf = (n) => n.replace(/\.pdf$/i, "")`. (Type/size **validation** is
  V2; V1 trusts `accept` + the backend.)
- **Mutation (N5/N6)** — `const qc = useQueryClient()`;
  ```ts
  const m = useMutation({
    mutationFn: () => uploadBook(file!, title.trim()),
    onSuccess: () => {            // N7
      qc.invalidateQueries({ queryKey: ["books"] });
      reset(); onClose();
    },
  });
  ```
  `reset()` clears `file`/`title` so a reopened dialog is fresh.
- **Form (U4/U5/U7)** — a `<form onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>`:
  - `<input type="file" accept="application/pdf" onChange={…} />` (U4).
  - title `<Input value={title} onChange={(e) => setTitle(e.target.value)} />` (U5),
    label "Title".
  - submit `<Button type="submit" disabled={!file || !title.trim()}>Upload</Button>`
    (U7). (The `isPending` busy state + server-error display are V2 — V1's submit
    just fires; on success the dialog closes.)

> The mutation's `error` and `isPending` exist on `m` but V1 doesn't render them
> (V2 wires `m.error` → inline message and `m.isPending` → busy submit). Wires to
> future slices are expected (slicing rules).

### 4. Library wiring (`app/page.tsx`) — A1, U1, U2, N1, N8 (via dialog), S1

- Add `const [open, setOpen] = useState(false)` (S1) and `const openDialog = () => setOpen(true)` (N1).
- **Header entry point (U1)** — make the header a flex row: the existing title +
  count block on the left, an `<Button onClick={openDialog}>Upload book</Button>`
  on the right.
- **Empty-state CTA (U2)** — pass the same button to `<Empty … action={<Button onClick={openDialog}>Upload book</Button>} />`.
- **Mount the dialog** — render `<UploadDialog open={open} onClose={() => setOpen(false)} />`
  once at the bottom of the `<section>` (outside the loading/empty/list branches so
  it's mountable from any state).
- The pending card (U3) needs no new code: `onSuccess`'s `invalidateQueries(['books'])`
  (N8) refetches `listBooks` (N2 → backend `GET /books`, N12), and the committed
  `pending` row renders through the existing `<BookCard/>` + `<StatusBadge status="pending"/>`.

## Styling (V1 = functional; polish is V3)

Plain but coherent with existing tokens (`text-ink`, `text-ink-muted`,
`bg-paper`/`bg-paper-raised`, `border-rule`). Give the `<dialog>` a minimal
panel + backdrop (`backdrop:bg-ink/20`, rounded bordered panel, max-width) so it
reads as a modal; V3 owns the real layout, the file-picker affordance, and
responsive polish.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; `make web`; then:

1. Open `/`. Empty library → the empty state shows an "Upload book" CTA; non-empty
   → the header shows an "Upload book" button.
2. Click it → the modal opens (Esc closes it and the trigger button is focusable
   again).
3. Pick a real PDF → the Title field auto-fills from the filename (edit it to
   confirm it's editable); Upload is enabled only with a file + non-empty title.
4. Click **Upload** → the dialog closes → a **`Pending`** `<BookCard/>` appears at
   the top of `/` (newest-first).
5. Wait / refresh → the backend ingest flips it toward `ready` (watching that flip
   live is Step 12).
6. `yarn lint` + typecheck clean.

## Out of V1 (later slices)

- **Client guards** (reject non-PDF, reject size > `MAX_UPLOAD_MB` before submit),
  **inline server errors** (413/422), **busy/in-flight submit**, **explicit Cancel
  button + backdrop-click-to-close** → V2.
- **`impeccable` pass** (dialog layout, file-picker affordance, states, responsive)
  → V3.
- **Re-upload / `book_id`**, **status polling**, **`failed` re-upload UX**, Delete,
  auth → out of Step 11 (shaping R8).
