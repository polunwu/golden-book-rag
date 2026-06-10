---
shaping: true
---

# Step 11 · V2 — Guards + error handling — Implementation Plan

Implements V2 of the Step 11 slices (`docs/v1/step11/slices.md`): the safety +
feedback layer over the **same dialog**, built without disturbing V1's submit
path. New: the client guards in the form (reject non-PDF, reject size >
`MAX_UPLOAD_MB` before the `POST`), the `MAX_UPLOAD_MB` config constant, one
inline-message surface (client guard **or** server `ApiError`), the in-flight
busy submit, and surfacing the mutation error. No `impeccable` pass (V3). Demoed
against the running backend with a real PDF.

> **Form library — `react-hook-form` (new dep).** V1's two-field form hand-rolled
> `useState` + a one-shot `safeParse`. V2's error handling is where that gets
> fragile (deriving messages by indexing `zod` issue paths; a persistent server
> error going stale across edits), so V2 adopts **react-hook-form** with a
> `zod`-resolver fed the **same colocated `uploadFormSchema`** (the project's
> "colocated zod form schema" convention, `CLAUDE.md` Frontend, is preserved —
> RHF consumes that schema rather than replacing it). RHF gives field-keyed
> `errors` (no path indexing) and a derived `isValid` for free; react-query keeps
> the async/server error (RHF owns *field* validation, not the mutation). This is
> the first FE form dep — scoped to the upload form; other forms (AskPanel) are
> untouched.

## What V1 already shipped (re-scoping V2)

V1's implementation pulled the **explicit close** (slices U8) forward: the
`<dialog>` already closes on the **×** button, on backdrop click (`onClick`
target === dialog), and on **Esc** (native `onClose` → `onClose` prop). So U8 is
**done** — V2 does **not** add a Cancel/close affordance. It stays as-is; the
only V2 interaction with it is the deliberate choice **not** to block close while
a mutation is in flight (a closed-mid-upload `onClose()` is a harmless no-op —
the `POST` finishes, the `pending` row is already committed server-side, and the
remount on next open resets fields).

What's actually left for V2: **U6, N3′, N4, N9, S4, S5, S6.**

> The mutation already lives in `BookUploadDialog` (`m.error`, `m.isPending`
> exist but are unrendered today — V1 noted these as wires to a future slice).
> V2 reads them.

## Where each piece lives (mechanism vs. fields split)

Per the project's dialog/form convention (`CLAUDE.md` Frontend): the **dialog
owns the mechanism** (mutation → `isPending`, `error`), the **form owns the
fields + client validation** (the type/size guards, the colocated
`uploadFormSchema`). RHF sits inside the form; it does **not** cross the boundary
into the mutation. So:

- **Client guards (N3′) + field errors (S4)** → `BookUploadForm`, via
  `useForm({ resolver, mode: "onChange" })` over the extended `uploadFormSchema`.
  RHF keys messages by field — `errors.file?.message` — so there's **no
  `issue.path` indexing** to break, and **no manual `clientError` derivation**:
  the resolver runs on every change, `isValid` gates submit.
- **Busy (S5) + server error (S6)** → owned by `BookUploadDialog` (the mutation),
  passed **down** as `pending` and `serverError` props. RHF deliberately does not
  own this — async/server state is react-query's job.
- **One inline-message slot (U6)** → rendered by the form: the file field error
  **or** the server error. They're made **mutually exclusive** (no precedence
  rule) by clearing the server error on edit — the form calls an `onDirty` prop
  on every field change, and the dialog wires it to `m.reset()`. So a stale
  server message can't outlive the inputs that caused it (the old hand-rolled
  `clientError ?? serverError` leaked exactly here: a valid edit after a failed
  POST re-exposed the dead server error).

Keeping U6 in the form means a single message location next to the fields it
explains, and the busy `Button` stays colocated with the submit it gates.

## Files

| File | Change |
|------|--------|
| `frontend/package.json` | **Add deps** `react-hook-form` + `@hookform/resolvers` (`yarn add`) |
| `frontend/src/lib/config.ts` | **Add** `MAX_UPLOAD_MB` (default 100; opt. `NEXT_PUBLIC_MAX_UPLOAD_MB`) — N4 |
| `frontend/src/components/books/BookUploadForm.tsx` | Rewrite on `useForm` + resolver over the extended `uploadFormSchema` (file type/size `.refine`, N3′); field errors via `errors.file` (S4); add `pending`, `serverError`, `onDirty` props; render the U6 inline message; busy submit label + disable (S5) |
| `frontend/src/components/books/BookUploadDialog.tsx` | Pass `m.isPending`, the friendly `m.error` message, and `onDirty={() => m.reset()}` down to the form (S5/S6/N9); keep the existing close affordances |

No schema change (the colocated `uploadFormSchema` stays in the form file, now
fed to a resolver), no API-client change, no backend change. `request<T>` already
maps `413`/`422` → friendly `ApiError` (`client.ts` `ApiError.friendly`).

## Steps

### 1. `MAX_UPLOAD_MB` config (`lib/config.ts`) — N4

Mirror the backend's `MAX_UPLOAD_MB` default (100) so the client guard rejects
**before** the `POST` rather than relying on the `413`:

```ts
// Client-side upload cap, mirrors the backend MAX_UPLOAD_MB (api/routers/books.py).
// A bad value falls back to 100 rather than NaN-disabling the guard.
const parsed = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB);
export const MAX_UPLOAD_MB =
  Number.isFinite(parsed) && parsed > 0 ? parsed : 100;
```

This is a **defense-in-depth** guard, not the source of truth — the backend still
enforces its own `_max_upload_bytes()` and can return `413`, which V2 surfaces
too (so a client/server mismatch still degrades to a server message, not a silent
pass).

### 2. Add the form deps

```sh
cd frontend && yarn add react-hook-form @hookform/resolvers
```

`@hookform/resolvers` carries `standardSchemaResolver` (`@hookform/resolvers/standard-schema`).
**zod is v4 here** and implements the Standard Schema spec, so use that resolver
— not the legacy `zodResolver`, whose zod-4 support is version-sensitive. (If a
pinned resolver version lacks the standard-schema entry, fall back to
`zodResolver` from `@hookform/resolvers/zod` after confirming it accepts the v4
schema; don't assume.)

### 3. Schema + form rewrite (`BookUploadForm.tsx`) — N3′, S4, U6, S5

Extend the colocated schema (the V1 comment already anticipates this: "the
type/size guards (V2) extend this with `.refine`"):

```ts
import { MAX_UPLOAD_MB } from "@/lib/config";

const MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

const uploadFormSchema = z.object({
  file: z
    .instanceof(File, { message: "Please choose a PDF file." })
    .refine((f) => f.type === "application/pdf", "Please choose a PDF file.")
    .refine(
      (f) => f.size <= MAX_BYTES,
      `That file is too large (max ${MAX_UPLOAD_MB} MB).`,
    ),
  title: z.string().trim().min(1),
});

type UploadFormValues = z.infer<typeof uploadFormSchema>;
```

- The `accept="application/pdf"` attribute only *filters* the OS picker; a user
  can still choose "All files" and pick a `.txt` (`f.type === "text/plain"`), so
  the `.refine` is the real guard. The `instanceof(File)` message covers the
  no-file case (the field defaults to `undefined`).

The form on RHF — props `{ onSubmit, pending, serverError, onDirty }`:

```tsx
const {
  register,
  handleSubmit,
  setValue,
  formState: { errors, isValid },
} = useForm<UploadFormValues>({
  resolver: standardSchemaResolver(uploadFormSchema),
  mode: "onChange",          // re-validate per keystroke/pick → live isValid + errors
});

// `file` is value-typed (File, not the input's FileList), so set it imperatively;
// `shouldValidate` runs the resolver, autofill writes the title field too.
const onFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
  onDirty();                                 // clear any stale server error
  const f = e.target.files?.[0];
  setValue("file", f as File, { shouldValidate: true });
  if (f) setValue("title", stripPdf(f.name), { shouldValidate: true });
};
```

- **File field (U4)** — a raw `<input type="file" accept="application/pdf" onChange={onFilePick}>`.
  It is **not** `register`ed (register would hand back the `FileList`); `setValue`
  is the value-typed path. `file` still validates because the resolver sees the
  set value.
- **Title field (U5)** — `register`ed, with `onDirty` on change so edits clear the
  server error too:
  ```tsx
  <Input
    placeholder="Book title"
    {...register("title", { onChange: () => onDirty() })}
  />
  ```
  `{...register}` spreads `name`/`onChange`/`onBlur`/`ref` onto `<Input>`, which
  forwards them to `<input>` (React 19 treats `ref` as a plain prop, so no
  `forwardRef` needed). Autofill via `setValue("title", …)` updates this
  uncontrolled input.
- **One inline-message slot (U6)** — the file field error, else the server error;
  mutually exclusive (the `onDirty`→`m.reset()` wiring keeps them from coexisting):
  ```tsx
  {errors.file ? (
    <Notice role="alert">{errors.file.message}</Notice>
  ) : serverError ? (
    <ErrorState detail={serverError} />
  ) : null}
  ```
  Client guard → muted `<Notice>` (an expectations nudge); server `ApiError` →
  `<ErrorState>` (a real failure), matching the AskPanel convention
  (`ErrorState detail={(mutation.error as Error).message}`). A blank title fails
  `isValid` (disables submit) **without** a message — consistent with V1's silent
  title gate, since `errors.file` is what the slot renders.
- **Submit (U7 / S5)** — `handleSubmit` only fires on a valid form; gate + label
  on `pending`, mirroring AskPanel's `"Asking…"`:
  ```tsx
  <form onSubmit={handleSubmit((v) => onSubmit(v.file, v.title))}>
    …
    <Button type="submit" disabled={!isValid || pending}>
      {pending ? "Uploading…" : "Upload"}
    </Button>
  </form>
  ```

The `onSubmit(file, title)` callback signature is **unchanged** from V1 (the
dialog still maps it to `m.mutate({ file, title })`), so the happy path is
behaviorally identical — only the form's internals move from `useState`+`safeParse`
to RHF.

### 4. Wire mutation state down (`BookUploadDialog.tsx`) — S5, S6, N9

The dialog already holds the mutation; pass its state — and the dirty hook — to
the form:

```tsx
<BookUploadForm
  key={String(open)}
  onSubmit={(file, title) => m.mutate({ file, title })}
  pending={m.isPending}
  serverError={m.error ? (m.error as Error).message : null}
  onDirty={() => m.reset()}        // edit clears a stale server error at the source
/>
```

- `m.error` is an `ApiError` whose `.message` is already friendly (`413` → "That
  file is too large.", `422` → the backend `detail`) — that **is** N9 ("write
  friendly `ApiError`"); no extra mapping in the dialog.
- **`onDirty` → `m.reset()`** is what makes the server error non-stale: the form
  calls it on every file pick / title keystroke, so `m.error` (hence the
  `serverError` prop) is cleared the moment the inputs change. `m.reset()` is a
  no-op when the mutation is already idle, so the per-keystroke calls are cheap.
- The remount on reopen (`key={String(open)}`) gives a fresh RHF instance (empty
  fields, no `errors`); combined with `onDirty`, a reopened dialog never shows a
  stale message.
- **Close affordances unchanged** — ×, backdrop, Esc all still call `onClose`.
  Not disabled during `pending` (see re-scoping note).

## Styling (V2 = functional; polish is V3)

Reuse `<Notice>` / `<ErrorState>` and the existing busy-label idiom — no new
visual system. V3 (`impeccable`) owns the inline-message placement/animation, the
busy affordance (spinner vs. label), and the file-picker error styling.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; `make web`; open the upload
dialog from `/`:

1. **Non-PDF guard** — pick a `.txt` (via "All files") → muted inline "Please
   choose a PDF file."; **Upload** disabled; **no** network request fires.
2. **Size guard** — pick a PDF over the cap (or set `NEXT_PUBLIC_MAX_UPLOAD_MB=1`
   and pick a >1 MB PDF) → inline "That file is too large (max N MB)."; Upload
   disabled; **no** request.
3. **Server error** — pick a valid PDF, force a backend failure (e.g. run the API
   with `MAX_UPLOAD_MB=0`) → submit → button shows **Uploading…** → on `413` an
   `<ErrorState>` shows "That file is too large."; the dialog stays open with
   fields intact.
4. **Server error clears on edit** (the staleness fix) — with that `<ErrorState>`
   showing, edit the title or re-pick a **valid** PDF → the server message
   disappears immediately (no stale "too large" over good input); it doesn't
   reappear until the next failing submit.
5. **Recover** — fix the file / restart the API at a sane cap → submit → success
   → dialog closes → **pending** card appears (V1 path intact).
6. **Busy state** — on a slow/large valid upload, the submit reads **Uploading…**
   and is disabled until the `202`.
7. **Close still works** — ×, backdrop click, and Esc each close the dialog
   (including mid-upload, harmlessly); reopening shows empty fields and no stale
   error.
8. `yarn lint` + typecheck clean.

## Out of V2 (later slices)

- **`impeccable` pass** — dialog layout, the real file-picker affordance, inline
  message + busy styling, responsive, empty-state CTA polish → V3 (restyles
  U1–U8).
- **Block-close-while-pending**, drag-and-drop, upload progress %, retry button,
  client/server cap reconciliation UI → out of Step 11 (shaping R8).
