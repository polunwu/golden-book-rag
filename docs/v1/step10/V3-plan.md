---
shaping: true
---

# Step 10 · V3 — `impeccable` pass — Implementation Plan

The final slice of Step 10 (`docs/v1/step10/slices.md`): **no new affordances** —
a styling + responsive cycle over what V1 and V2 already render (U3–U16). The
behavior, data flow, schemas, client fns, and backend are all **frozen**; V3 only
touches markup/classes and two small structural seams (answer-spacing decoupling,
compare-view width). Demoed before/after against an API-seeded `ready` book, at
desktop and narrow widths, including the refusal + compare states.

This pass works **inside the existing design system** (the paper/ink editorial
tokens in `globals.css`: serif body via `--font-serif`, sans for meta/UI, `ink`/
`ink-muted`/`rule`/`paper`/`paper-raised`, `status-*`). It does **not** introduce
a new palette, new fonts, or a component library. It reuses the `ui/` primitives
(`Button`, `Input`, `Notice`, `Skeleton`) and matches the Library's restraint
(`app/page.tsx`, `layout.tsx`).

## Design intent (what "impeccable" means here)

1. **Citations are the product.** The grounded answer is the headline; the
   Sources list is the proof, and must read as first-class — not a footnote.
   Most of the polish budget goes to the answer block and the citation cards.
2. **Honest comparison.** In compare mode the two columns must read as *peers*
   with a clear "this one is grounded, this one isn't" signal — the retrieval
   column visibly carries sources; the plain column visibly doesn't. No column
   should look broken for lacking citations.
3. **Calm editorial restraint.** Serif answer prose at a comfortable measure;
   sans only for chrome/meta. One accent (`status-processing` amber, already the
   marker/focus color) used sparingly. No gradients, shadows-as-decoration, or
   motion beyond the existing transient highlight.

## Key decisions

### D1 — Compare view breaks out of the reading column (recommended)

The shared `<main>` is `max-w-3xl` (`layout.tsx:32`, ~728px of content). V2's
compare grid (`AskPanel.tsx:83`, `md:grid-cols-2`) therefore renders two ~350px
columns — too tight for full-text citation cards. **Recommendation:** on `lg:`
only, let the compare grid (and *only* the compare grid) break out to a wider
centered band (~`max-w-5xl`/64rem), leaving the header, input, toggle, refusal,
and the **single-column** answer at the editorial `max-w-3xl` width.

- Single-column answer (compare off / V1 path) **stays `max-w-3xl`** — the
  reading measure is correct for one grounded answer. Only the side-by-side view
  widens, because it's a comparison surface, not a reading surface.
- Implement as a self-contained breakout on the book page so the shared
  `layout.tsx`/Library are **untouched**. Use a viewport-centered wrapper around
  the compare grid (e.g. a `lg:` full-width re-center: `lg:mx-[calc(50%-50vw)]`
  + inner `lg:mx-auto lg:max-w-5xl lg:px-5`), or hoist the wider max-width to the
  book page `<section>` and re-constrain the non-compare blocks to `max-w-3xl`.
  Pick whichever reads cleaner in review; keep it in one place.
- Below `lg` the grid **stacks to one column** (retrieval first, then plain) —
  two 350px columns on a tablet is worse than stacked.
- **Fallback if the breakout feels too clever:** keep everything at `max-w-3xl`
  and just raise the two-column breakpoint to `lg:` (stack on `md`). Less ideal
  for the cards but zero layout risk.

### D2 — Decouple `<AnswerView/>`'s outer spacing

`<AnswerView/>` owns its own top margin (`mt-6`, `AnswerView.tsx:62`). In a
compare column it sits under an `<h2>` heading, so the gap doubles (the V2 plan
flagged this as V3's to fix). **Fix:** remove the outer `mt-6` from
`<AnswerView/>`'s root and let each *caller* own the gap — the single-column
render and each compare `<section>` add their own spacing. This makes
`<AnswerView/>` a self-contained block that composes cleanly in both layouts.

### D3 — Answer loading skeleton

V1/V2 only signal in-flight via the button text ("Asking…"); the answer region
stays empty. For an impeccable feel (and because compare fires two calls), add a
lightweight **answer skeleton** while `mutation.isPending`: a few `Skeleton`
lines for the prose + 1–2 faux citation cards, mirroring the real layout (one
column normally, two when `compare` is on). Reuse the `Skeleton` primitive;
respect the existing `prefers-reduced-motion` rule (already global in
`globals.css`). This is the one piece that touches a *state* V1/V2 left bare —
it adds no new affordance, just a rendered loading treatment for U9.

## Files

| File | Change |
|------|--------|
| `frontend/src/app/books/[id]/page.tsx` | Header polish (title scale/weight, badge baseline alignment, back-link); host the compare-view width breakout (D1); refine `BookSkeleton` to preview the real header + input shape |
| `frontend/src/components/AskPanel.tsx` | Group input+Ask; restyle the compare toggle; compare-grid polish — column headers, peer framing, divider/gap, responsive stack (D1); answer-loading skeleton (D3); caller-owned answer spacing (D2) |
| `frontend/src/components/AnswerView.tsx` | Answer prose typography (serif measure/leading); `[n]` marker chip styling; refusal treatment; drop owned outer margin (D2) |
| `frontend/src/components/Citations.tsx` | Citation-card hierarchy — marker chip, meta row legibility, full-text block, hover affordance, keep the transient highlight |
| `frontend/src/components/ui/Skeleton.tsx` | Only if the answer skeleton needs a shape the primitive can't express via `className` (prefer composing the existing one — likely no change) |

No changes to: `api/books.ts`, `api/client.ts`, `schemas/*`, `lib/format.ts`,
`StatusBadge`, `ErrorState`, `Notice`/`Button`/`Input` internals,
`layout.tsx`/`page.tsx` (Library), or any backend file.

## Steps

### 1. Book page (`app/books/[id]/page.tsx`) — U3–U5

- **Header:** keep `bookTitle(book!)` null-safe; tune the title (serif, larger/
  tighter — it's the page subject), align `<StatusBadge/>` to the title baseline
  (the header is already `flex flex-wrap items-baseline`). Back-link styling is
  already coherent with the nav; leave or lightly unify.
- **Breakout host (D1):** wrap so the header + `<AskPanel/>`'s non-compare
  content stay `max-w-3xl` while the compare grid can widen on `lg:`. Keep the
  mechanism in one place; don't leak width logic into three files.
- **`BookSkeleton`:** make it preview the *real* first paint — a title bar, a
  meta line, and an input-shaped block — so the loading→loaded transition
  doesn't jump. (Already close at `page.tsx:13`; refine proportions.)

### 2. `<AskPanel/>` (`components/AskPanel.tsx`) — U6–U11, U15

- **Input + Ask:** the `sm:flex-row` group is right; refine alignment/spacing so
  the button reads as the primary action paired to the field. No new primitive.
- **Compare toggle (U7):** restyle the bare checkbox+label (`AskPanel.tsx:64`)
  into a deliberate control — either a styled checkbox or a small switch built
  from existing tokens (`rule`/`ink`/`status-processing`), with the same
  `disabled` gating (`!ready || isPending`). Keep it a `<label>`-wrapped native
  input for a11y; style, don't replace, the semantics.
- **Gate notice / error placement (U10/U11):** already `<Notice/>` / `<ErrorState/>`;
  just verify rhythm/spacing in the new layout.
- **Answer skeleton (D3):** when `mutation.isPending`, render the skeleton in the
  answer slot — one column, or two columns when `compare` is on (read the live
  flag here; it only affects the *placeholder* shape).
- **Compare grid (U15 / D1):** keep the **single-column path byte-compatible in
  behavior** (one `<AnswerView/>` fed the RAG response). For the two-column path:
  - Column headers reframed as peers: "Grounded in this book" / "Plain LLM (no
    sources)" (or similar) — the label itself carries the honest-comparison
    signal (intent #2). Use sans, muted, with the retrieval side subtly
    foregrounded.
  - A divider or generous gap between columns; stack on narrow (`lg:grid-cols-2`,
    one column below).
  - Each `<section>` owns its top gap now that `<AnswerView/>` doesn't (D2).

### 3. `<AnswerView/>` (`components/AnswerView.tsx`) — U12–U14

- **Prose (U12):** serif body at a comfortable measure and leading
  (`whitespace-pre-wrap` stays — the backend returns paragraphed text). This is
  the hero block; give it the most typographic care.
- **Marker chips (U13):** the inline `[n]` button (`AnswerView.tsx:74`) is the
  bridge to the proof. Refine into a small, legible, tappable chip (clear hit
  target, the amber accent, visible focus — keep the existing
  `focus-visible:ring`). Don't lose the inert-`[n]` fallback for a marker without
  a citation (`AnswerView.tsx:83`).
- **Refusal (U14):** the current generic `<Notice/>` (`AnswerView.tsx:63`) is
  fine but blunt. Give the refusal a calm, distinct treatment (still
  `status`-role, muted) that reads as "couldn't ground an answer," shown above
  the answer text — citations are already `[]` so Sources stays absent.
- **Spacing (D2):** remove the root `mt-6`; the caller owns the gap.

### 4. `<Citations/>` (`components/Citations.tsx`) — U16 (the product)

- Keep: `null` on empty, the `id={cite-${marker}}` + `registerRef` scroll target,
  the `highlighted` transient flash (`transition-colors duration-300`), full
  always-visible text (no expander — D3 from shaping).
- **Card hierarchy:** make each `<li>` (`Citations.tsx:28`) read as a citation
  card with clear order: marker chip (echo the in-prose chip so the link reads
  visually) → meta row (breadcrumb › page range · score) → the full quoted text.
  Improve the meta row legibility (`Citations.tsx:38`) and the body block
  (`Citations.tsx:50`).
- **Score:** keep it honest and small (`score 0.72`); it's provenance, not a
  headline — style as muted meta, don't gamify into bars/stars.
- **Hover/affordance:** a subtle hover on the card (it's a scroll target) without
  implying it's a button. Preserve the strong `highlighted` state (the amber
  border + tint) as the click feedback.

### 5. Cross-cutting

- **Responsive sweep:** verify header wrap, input→button stack (`sm:`), compare
  stack (`lg:`), and citation meta-row wrap at ~360px and ~1280px.
- **Reduced motion:** the global rule (`globals.css:36`) already neutralizes the
  highlight transition + smooth scroll; confirm nothing new bypasses it.
- **a11y:** preserve existing roles/labels (`aria-label` on markers, `role` on
  notices/alerts, focus rings). Color is never the *only* signal (the compare
  framing uses text labels; refusal uses a worded notice).

## Styling guardrails

- Only `globals.css` tokens + Tailwind utilities. **No** new theme vars, fonts,
  shadow-heavy cards, or a UI kit. If a value recurs, prefer an existing token.
- Don't change component **props/signatures** except removing `<AnswerView/>`'s
  owned outer margin (D2) — that's the one structural seam. Everything else is
  class-level.
- Match the Library's density and quiet (`app/page.tsx`); the book page should
  feel like the same product, one level deeper.

## Demo / acceptance

`make db-up && make db-migrate && make api-dev`; seed a book to `ready`;
`make web`; open `/books/{id}`. Capture **before/after** for each:

1. **Header + input** at desktop and ~360px — title/badge/back-link aligned, no
   wrap breakage; input→button stacks cleanly on narrow.
2. **Single grounded answer** (compare off) — serif prose at a good measure;
   inline `[n]` chips legible and tappable; click `[n]` → smooth scroll + flash
   on its card; Sources read as first-class cards (marker, breadcrumb, pages,
   score, full text).
3. **Refusal** — distinct calm treatment, answer text shown, no Sources.
4. **Compare on** — two peer columns, the grounded/plain framing obvious; on
   `lg:` the grid uses the wider band (D1) so cards breathe; on narrow it stacks
   (retrieval first). Single-column path unchanged when compare off.
5. **Loading** — answer skeleton matches the about-to-render layout (one or two
   columns); no empty gap, no jump on resolve.
6. **Error / gate** — `<ErrorState/>` and gate `<Notice/>` sit correctly in the
   new rhythm; compare checkbox disabled with the gate.
7. **Reduced motion** on → highlight/scroll are instant, no animation.
8. `yarn lint` + typecheck clean; no behavior/network change vs. V2 (still one
   `/ask` off, two on).

## Out of scope (not this slice / not this step)

- Any new affordance, schema, client fn, or backend change (frozen).
- Streaming, per-column skeletons tied to each call's state, caching the plain
  answer across re-asks, a `k`-UI, expandable citations, dark mode — out of Step
  10 (shaping R8).
- Reworking the shared `layout.tsx` width for all routes — V3 confines the
  breakout to the book page.

## Note on execution

This is a visual cycle — a good fit for the `impeccable` workflow once the plan
is approved. Run it iteratively against the live app (seed a `ready` book, drive
the real `/ask` responses) so the answer/citation typography and the compare
band are tuned on real content, not lorem.
