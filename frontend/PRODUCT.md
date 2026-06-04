# Product

## Register

product

## Users
Readers and researchers who upload a PDF book and then ask grounded questions
about it. They arrive with a specific book and a specific question; the task on
any screen is to find or trust an answer drawn from that book. Context is focused
reading/research, not glanceable dashboards.

## Product Purpose
BookRAG puts a usable UI on a retrieval-augmented backend: upload a PDF, watch it
become searchable, then ask questions and read grounded answers with page and
section citations. Success is a reader who trusts the answer because they can see
the passages behind it. The Library is the front door: it shows the books a user
has, their ingest status, and the way into each one.

## Brand Personality
Quiet, literary, trustworthy. A reading room, not a control panel. The interface
recedes so the books are the subject: serif headings, ink-on-paper warmth,
generous whitespace, color reserved for status and primary actions. Three words:
calm, bookish, exact.

## Anti-references
Generic SaaS dashboards: gradient heroes, identical icon+heading+text card grids,
tiny tracked uppercase eyebrows above every section, cramped admin tables. Nothing
should read as "AI workflow tool." No decorative motion.

## Design Principles
- **Citations are the product.** Trust comes from showing the receipts; invest
  where provenance renders (status, page ranges, section breadcrumbs).
- **The tool recedes.** Earned familiarity over novelty; the reader's book and
  question are the subject, the chrome is quiet.
- **Ship the core loop, leave the seams.** Each screen does its one job well;
  later-step affordances are added by the steps that own them, not stubbed early.
- **Honest states.** Loading, empty, error, and refusal are first-class, designed
  states, never afterthoughts.

## Accessibility & Inclusion
WCAG AA contrast on all text (including small meta and placeholders), visible
keyboard focus indicators on every interactive element, and a
`prefers-reduced-motion` alternative for every animation. The app is deliberately
non-indexed; auth is the real privacy gate (later step).
