---
shaping: true
---

# Step 11 · V3 — `impeccable` pass — Implementation Plan

The final slice of Step 11 (`docs/v1/step11/slices.md`): **no new affordances** —
a styling + responsive cycle over what V1 and V2 already render (U1–U8). The
upload behavior, data flow, schemas, the `uploadBook` client fn, the
`uploadFormSchema` guards, the RHF wiring, and the backend are all **frozen**; V3
is **markup/classes only — no behavioral change** (close stays × + Esc;
backdrop-click-close is deliberately not added — see D4).
Demoed before/after against the running backend with a real PDF, at desktop and
narrow widths, including the empty-state CTA, a guard error, the server-error
surface, and the busy/submit state.

This pass works **inside the existing design system** (the paper/ink editorial
tokens in `globals.css`: serif body via `--font-serif`, sans for meta/UI,
`ink`/`ink-muted`/`rule`/`paper`/`paper-raised`, `status-*`). It does **not**
introduce a new palette, new fonts, or a component library. It reuses the `ui/`
primitives (`Button`, `Input`, `FieldError`, `ErrorState`, `Empty`, `Skeleton`)
and matches the restraint of the Library (`app/page.tsx`) and the Ask page
(Step 10's polish), so the upload moment feels like the same product.

## Design intent (what "impeccable" means here)

1. **The file is the subject.** Upload is a one-decision moment — "which PDF?".
   The polish budget goes to the **file-picker affordance**: a real, generous
   "choose a PDF" target (not the browser's raw `Choose File` button), that on
   pick reads back the *filename + size* so the user trusts they grabbed the
   right book. Everything else (title, submit) is secondary chrome around it.
2. **Calm, reversible, honest.** The dialog should feel light to open and easy
   to dismiss (× + Esc), never trap the user, and never lie about
   state — a guard error reads as an *expectations nudge* (muted), a server
   failure reads as a *real failure* (`ErrorState`), and the busy submit is
   unmistakably in-flight without blocking the close.
3. **No layout jank.** Picking a file, surfacing/clearing a field error, and the
   pending→done transition must not shift the form. Reserve space (the
   `FieldError` min-height idiom is already correct); the file target keeps a
   stable height across empty/chosen/error.

## Key decisions

### D1 — Real file-picker affordance (the centerpiece)

Replace the raw `<input type="file">` (today: `font-sans text-sm text-ink`,
i.e. the native gray `Choose File` button) with a **styled `<label>`-as-target**
wrapping a visually-hidden (`sr-only`) native input:

- The whole region is the click target; because it's a `<label>` over a real
  `<input>`, keyboard activation + the file dialog come for free — **no
  hand-rolled button-fires-input**. Add a `focus-within:` ring (mirror
  `Input`/`Button`'s `focus-visible:ring-status-processing`) so it's visibly
  focusable.
- **Two states, one stable height:**
  - *Empty* — a dashed-`rule` bordered panel: a small document/upload glyph (inline
    SVG, currentColor), "Choose a PDF", and a muted hint ("or drag it here" if D2
    lands; else "PDF up to {MAX_UPLOAD_MB} MB").
  - *Chosen* — solid-`rule` border, the **filename** (truncated, `title=` full
    name) + **formatted size** (`formatBytes`, D3-helper) + a muted "Replace"
    affordance. Read the picked file with RHF `watch("file")` — a **read**, no
    new state, no new affordance.
- **Error styling** — when `errors.file`, the target border turns `status-failed`
  and `aria-invalid` is set (already wired); the message still renders in the
  existing `<FieldError>` slot below (no jump — reserved min-height).
- Keep `accept="application/pdf"`, `onChange`, and the existing
  `setValue("file", …, { shouldValidate: true })` + title-autofill path
  untouched — only the *markup around* the input changes.

### D2 — Drag-and-drop on the target (optional nicety, rides the pass)

Shaping R8.3: drag-drop is "at most an `impeccable` nicety, not a must-have." The
styled target makes it nearly free: add `onDragOver` (preventDefault +
drag-active border tint) and `onDrop` to the label, routing the dropped file
through the **same** handler as the picker. Refactor `onFilePick(e)` into a
shared `handleFile(f: File | undefined)` consumed by both `onChange` and
`onDrop` (and by "Replace"). **Recommended to include** since the target already
exists; **droppable** if review prefers the minimal surface — it adds no
must-have and is pure addition over D1.

### D3 — Busy affordance (spinner in the submit)

V1/V2 signal in-flight via the button label only (`"Uploading…"` + disabled).
For the impeccable feel, add a **small inline spinner** before the label inside
the submit `<Button>` while `pending` — a `border`-based spin (`animate-spin`),
rendered at the **call site** (don't add a prop to the generic `Button`). The
global `prefers-reduced-motion` rule (`globals.css:36`) already neutralizes the
animation, so reduced-motion users get a static label, no extra code. A tiny
`formatBytes(n)` helper (used by D1's chosen-state) goes in `lib/format.ts`
alongside `formatDate`/`pageRange` (it's a display formatter, same family).

### D4 — No backdrop-click-close (decided out)

Backdrop-click-to-close was considered and **removed by the user** — the dialog
closes on the **× button + Esc** only. A native `<dialog>` opened with
`showModal()` does not light-dismiss by default, so this is simply *not adding*
an `onClick`-on-backdrop handler; V3 introduces **no behavioral change** at all.

> **Doc note:** `V2-plan.md`'s re-scoping note claims V1 "already closes … on
> backdrop click (`onClick` target === dialog)" — that was never in the shipped
> `BookUploadDialog.tsx`, and with backdrop-close now decided out it stays false.
> Correct that line in `V2-plan.md` (close affordances are × + Esc) when
> convenient, so the docs don't assert an affordance that doesn't exist.

V3 still styles the `::backdrop` (already `backdrop:bg-ink/20`) and may add an
optional subtle open transition (`@starting-style` + `transition` on the panel,
reduced-motion-safe) — both are pure styling, no dismiss behavior.

### D5 — Entry-point + dialog chrome

- **Entry points (U1/U2):** the header `<Button>Upload</Button>` and the
  empty-state CTA both read "Upload" today. Unify the label to **"Upload book"**
  (the affordance name throughout the docs) and add a small leading upload glyph
  to the header button so it reads as the page's primary action. The empty-state
  CTA already routes through `Empty`'s `action` slot — keep it prominent; verify
  it's the clear focal CTA on an empty library.
- **Dialog chrome (U6/U7/U8):** tune the header (title scale/weight, the × hit
  target + focus ring — already decent at `BookUploadDialog.tsx:46`), the panel
  padding/rhythm, and the submit row. Confirm the `ErrorState` server-error slot
  and the per-field `FieldError`s sit in a consistent vertical rhythm with the
  new file target.

## Files

| File | Change |
|------|--------|
| `frontend/src/components/books/BookUploadForm.tsx` | The file-picker affordance (D1): `sr-only` input inside a styled `<label>` target, empty/chosen states via `watch("file")`, error border; optional drag-drop (D2) via a shared `handleFile`; busy spinner in the submit (D3); message-rhythm polish. **No prop/signature change**, no schema/RHF-logic change. |
| `frontend/src/components/books/BookUploadDialog.tsx` | Dialog chrome polish (header, ×, panel, `::backdrop`); optional open transition. No mutation/wiring change, **no dismiss-behavior change** (× + Esc only — D4). |
| `frontend/src/app/page.tsx` | Entry-point polish (D5): unify label to "Upload book", header-button glyph, verify empty-state CTA prominence. |
| `frontend/src/lib/format.ts` | **Add** `formatBytes(n)` for the chosen-file size readout (D1/D3). |

No changes to: `api/books.ts`, `api/client.ts`, `schemas/*`, `lib/config.ts`,
`uploadFormSchema` / the RHF resolver + validation logic, the `Button`/`Input`/
`FieldError`/`ErrorState`/`Empty` primitive **internals** (styled at the call
site, not edited), `StatusBadge`/`BookCard`, `layout.tsx`, or any backend file.

## Steps

### 1. `formatBytes` (`lib/format.ts`) — D1/D3 helper

A small display formatter beside the existing ones:

```ts
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}
```

### 2. File-picker affordance (`BookUploadForm.tsx`) — D1/D2

- Refactor the picker handler into a shared `handleFile`:
  ```tsx
  const handleFile = (f: File | undefined) => {
    onDirty();
    setValue("file", f as File, { shouldValidate: true });
    if (f) setValue("title", stripPdf(f.name), { shouldValidate: true });
  };
  ```
  `onChange={(e) => handleFile(e.target.files?.[0])}`; (D2) `onDrop` reads
  `e.dataTransfer.files?.[0]`, `onDragOver`/`onDragLeave` toggle a drag-active
  border tint. **The validation contract is unchanged** — `shouldValidate` still
  runs `uploadFormSchema` against the set `File`.
- The target markup: a `<label>` (`relative flex … rounded-lg border` —
  **dashed** `border-rule` when empty, **solid** when chosen, `border-status-failed`
  when `errors.file`, `focus-within:ring-2 focus-within:ring-status-processing`)
  wrapping `<input type="file" accept="application/pdf" className="sr-only" …>`.
  Render the empty vs. chosen state off `const file = watch("file")`:
  filename (truncated, `title={file.name}`) + `formatBytes(file.size)` + a
  "Replace" hint when chosen; glyph + "Choose a PDF" + size hint when empty.
- Keep the `<FieldError message={errors.file?.message} />` exactly where it is
  (below the target) — its reserved height already prevents jump.

### 3. Title field + message rhythm (`BookUploadForm.tsx`) — U5/U6

- The title `<Input>` (`register("title", { onChange: () => onDirty() })`) stays;
  only spacing/label polish around it. The autofilled value must remain visible
  and editable (it is — uncontrolled `<input>` updated via `setValue`).
- The form-level server-error `<ErrorState>` (cleared on edit via `onDirty →
  m.reset()`) stays; verify it sits with consistent spacing above the submit row
  and doesn't fight the per-field errors.

### 4. Busy submit (`BookUploadForm.tsx`) — U7/S5/D3

```tsx
<Button type="submit" disabled={!isValid || pending}>
  {pending && <Spinner />}{pending ? "Uploading…" : "Upload"}
</Button>
```

`Spinner` is a tiny inline element (a bordered `animate-spin` span, currentColor),
**colocated** in the form file or added to `ui/` only if it'd be reused — prefer
inline; don't thread a `loading` prop into the generic `Button`. Reduced-motion
is handled globally.

### 5. Dialog chrome (`BookUploadDialog.tsx`) — D5

- Keep `onClose`, the `showModal()`/`close()` sync effect, ×, and Esc as-is —
  **no dismiss-behavior change** (no backdrop `onClick`, D4).
- Polish the header (title, ×), panel padding, and `::backdrop`. Optional: a
  subtle open transition via `@starting-style` on the panel — only if it reads
  clean in review; reduced-motion must no-op it.

### 6. Entry points (`app/page.tsx`) — D5/U1/U2

- Unify both buttons to "Upload book"; add a small upload glyph to the header
  button. Confirm the empty-state CTA (through `Empty`'s `action`) is the clear
  focal action.

### 7. Cross-cutting

- **Responsive sweep:** at ~360px the dialog is `w-[min(28rem,calc(100vw-2rem))]`
  (already fluid) — verify the file target, filename truncation, title field, and
  submit row don't overflow; the header entry button shouldn't crowd the title +
  count on narrow (it's `flex items-start justify-between` today).
- **Reduced motion:** the global rule neutralizes the spinner, any open
  transition, and the drag tint transition — confirm nothing bypasses it.
- **a11y:** preserve `aria-invalid`, the `<FieldError role="alert">`/`<ErrorState
  role="alert">` semantics, the × `aria-label`, the native focus-trap; the
  `sr-only` input keeps the label↔input association so screen readers still
  announce a file field, and keyboard users reach it via the label's
  `focus-within` ring.

## Styling guardrails

- Only `globals.css` tokens + Tailwind utilities. **No** new theme vars, fonts,
  shadow-heavy cards, or a UI kit. One accent (`status-processing` amber) for
  focus/active, used sparingly; `status-failed` only for error borders/text.
- **No prop/signature changes** to components and **no logic changes** to the
  RHF form or `uploadFormSchema` — V3 is class-level markup plus the `handleFile`
  refactor (behavior-preserving); no dismiss-behavior change (D4).
- Match the Library's density and quiet; the dialog should feel like the same
  product, one modal deep.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; `make web`; open `/`. Capture
**before/after** for each:

1. **Entry points** — empty library shows a prominent "Upload book" CTA; a
   non-empty library shows the header "Upload book" button (with glyph), aligned
   with the title/count, no wrap breakage at ~360px.
2. **File-picker affordance** — open the dialog: the file target reads as a real
   "choose a PDF" zone (not the native gray button); pick a PDF → it shows the
   filename + size + "Replace", title autofills; (D2) drag a PDF onto the target
   → same result.
3. **Guard error** — pick a `.txt` (via "All files") → the target border goes
   `status-failed`, the muted "Please choose a PDF file." renders below with **no
   layout jump**; submit disabled; **no** network call. Oversize → "too large"
   the same way.
4. **Busy** — valid PDF → submit shows the spinner + "Uploading…", disabled until
   `202`; reduced-motion → static label, no spin.
5. **Server error** — force a backend failure (`MAX_UPLOAD_MB=0` server-side) →
   `<ErrorState>` shows the friendly message, dialog stays open, fields intact;
   editing the title / re-picking clears it immediately (V2 staleness fix intact).
6. **Dismiss** — × and Esc each close the dialog (incl. mid-upload, harmlessly);
   a backdrop click does **not** close (decided out, D4); reopening shows empty
   fields, no stale error.
7. **Success** — valid PDF → submit → dialog closes → **pending** `<BookCard/>`
   appears at the top of `/` (V1 path unchanged).
8. `yarn lint` + typecheck clean; **no behavior/network/schema change** vs. V2
   (markup only).

## Out of scope (not this slice / not this step)

- Any new affordance, schema, client fn, RHF/validation logic change, or backend
  change (frozen) — V3 is markup only; no dismiss-behavior change (D4).
- Upload **progress %**, **retry** button, block-close-while-pending, multi-file
  upload, client/server cap reconciliation UI — out of Step 11 (shaping R8).
- **Re-upload by `book_id`**, **`failed`→re-upload UX**, **live status polling**
  (`pending→ready` in place), **Delete**, **auth**, dark mode — later steps
  (R8.1–R8.4).

## Note on execution

This is a visual cycle — a good fit for the `impeccable` workflow once the plan
is approved. Run it iteratively against the live app (a real PDF, the real
`202`/`413`/`422` responses) so the file target, the chosen-file readout, the
and busy spinner are tuned on real interaction, not a mock. Close stays × + Esc
(backdrop-close decided out, D4); correct the stale `V2-plan.md` backdrop-close
line when convenient.
