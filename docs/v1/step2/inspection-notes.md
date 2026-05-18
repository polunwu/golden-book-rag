# Step 2 Inspection Notes

Manual inspection of `temp/chunks.json` from running the chunker on `temp/books/AI_ENGINEERING_BUILDING.pdf` (Chip Huyen, *AI Engineering*, O'Reilly, 535 pages). Captured 2026-05-18.

Settings: `CHUNK_SIZE=1024`, no overlap, block-aware accumulation with sentence fallback.

---

## Summary stats

| Metric | Value |
|---|---|
| Total chunks | 1284 |
| PDF pages | 535 |
| Pages covered | 535 (100%) |
| Avg chunk length | 837 chars (~209 tokens) |
| Min / Max | 274 / 1024 chars |
| Chunks > 1024 | 0 |
| Chunks < 200 | 0 |
| Multi-page chunks | ~29% |
| Chunks with empty `section_path` | 0 |

`section_path` is always populated because the sample PDF's TOC starts at page 1 (`Cover`). On PDFs without an early TOC entry, pre-TOC chunks would correctly fall through to `[]`.

---

## What looks right

- No mid-word or mid-sentence cuts — block boundaries from `get_text("blocks")` keep fragments coherent.
- Length distribution clusters near upper bound (72% in 768–1024 chars), expected for greedy packing.
- Section transitions clean: `Cover → Copyright → Table of Contents → Preface → Preface/What This Book Is About → ...` flow matches the book.
- Every page contributes at least one chunk; no page silently dropped.
- Last chunk lands at `pages 534-535` with `section=['Colophon']` — book end reached correctly.

---

## Observed artifacts (not fixed — log for later)

### 1. TOC dot-leaders survive as fragments ✅ resolved

Previously: 16 chunks contained `. . . . . . .` patterns from TOC dot-leaders; one chunk (idx=8, page 7) was just 27 chars of dots.

**Fix applied:** `_is_noise(text)` in `services/chunker.py` drops any block whose `.` + whitespace ratio exceeds 50% before it enters the packing buffer.

**Result:** 26 noise chunks removed (1310 → 1284 total); dot-leader pattern count 16 → 0; min chunk length 27 → 274 chars.

### 2. Multi-space + tab residue from PDF layout

- 100 chunks contain runs of 2+ spaces (column gaps preserved by PyMuPDF)
- 3 chunks contain literal `\t` (mostly `•\t` bullet indentation)

Probably harmless for embedding similarity but cosmetically ugly when surfaced to users in retrieval results.

**Mitigation candidates:** post-process each chunk text with `re.sub(r"\s+", " ", text).strip()` before save.

### 3. Cover-page metadata pollutes first chunks

Chunks 0–5 mix ISBN, price, barcode digits with marketing blurbs:

```
'Chip Huyen AI Engineering Building Applications \nwith Foundation Models 9\n7 8 1 0 9 8 1 6 6 3 0 4 5 7 9 9 9 ISBN:   978-1-098-16630-4 ...'
```

Low semantic value; will rarely be useful retrieval targets.

**Mitigation candidates:** skip TOC + front matter pages by section filter, or drop chunks whose `section_path` ∈ {`Cover`, `Copyright`, `Table of Contents`}.

### 4. Multi-page chunks at section boundaries

29% of chunks span 2 pages. This is by design (greedy block packing crosses page boundaries when buffer has room) and is good — keeps coherent paragraphs together. Worth noting that `page_start` is used for section lookup, so a chunk straddling a section change will be tagged with the *earlier* section. Cross-section straddles in the sample appear infrequent in narrative chapters.

### 5. Reading order assumption

PyMuPDF `get_text("blocks")` returns blocks in PDF object order, which is usually top-to-bottom but **not guaranteed** for multi-column layouts. This book is single-column so no issue observed, but for two-column papers we'd need `sort=True` or coordinate-based sorting.

---

## Open questions

- Should `section_path` be set from `page_start` or from majority-page of the chunk's fragments? (Current: `page_start`. Probably fine.)
- Is char-based `CHUNK_SIZE` good enough vs. token-based? Char count overestimates tokens for English (~4 chars/token) but underestimates for code. For this corpus (English prose), fine.
- Worth filtering very short chunks (< 100 chars) before save? Saves storage; some short chunks (chapter titles, callouts) may have value.

---

## Next-step impact

For Step 3 (embeddings):

- 1310 chunks × `text-embedding-3-small` ≈ ~1310 API calls (or batched). At avg 209 tokens/chunk, total ~274K tokens ≈ $0.005 at current pricing. Negligible.
- Noise chunks (dot-leaders, ISBN strings) will get embedded but should retrieve poorly; not blocking for V1.
- Recommend revisit filtering after building eval set — measure retrieval precision impact before adding cleanup code.
