# Research: RAG Chunk Size & Overlap (2026)

Snapshot of current technical consensus collected 2026-05-18 to inform Step 2 chunker decisions. Used to justify `CHUNK_SIZE=1024` chars (~256 tokens) and no overlap.

---

## Chunk Size

### Consensus default

- **256–512 tokens** covers most RAG use cases
- **512 tokens + 50–100 token overlap** = benchmark-validated default; 69% accuracy in largest real-document test of 2026 (Firecrawl 2026 guide)
- Starting point recipe: 512 tokens + 10–20% overlap, then measure on your actual query set and adjust

### Query-type dependence

| Query type | Recommended chunk size |
|---|---|
| Factoid Q&A | 256–512 tokens |
| Analytical / multi-hop | 512–1024 tokens |
| Summarization (narrative flow) | 512–1024 tokens |
| Legal / clause-bounded | Semantic boundaries matter more than size |

### Long-context LLMs don't kill chunking

Even with 128K+ token windows, chunking remains essential:
- Retrieved context must still fit alongside instructions, examples, persona
- Larger retrieved context worsens "needle in a haystack" — relevant tokens get diluted
- Cost scales with input tokens regardless of model context length

---

## Overlap

### Mixed evidence — DO NOT default to 20%

| Study (2025–2026) | Finding |
|---|---|
| Jan 2026 systematic analysis — SPLADE retrieval + Mistral-8B on Natural Questions | **Overlap provided no measurable benefit on recall**; only increased indexing + embedding cost |
| NVIDIA — FinanceBench, 1024-token chunks, dense retrieval | Tested 10/15/20%; **15% optimal** |
| MDPI Bioengineering Nov 2025 — clinical decision support | Adaptive chunking aligned to topic boundaries: **87%** accuracy vs **13%** for fixed-size baseline |

### When overlap helps

- Dense embedding retrieval on long-context analytical queries
- Corpora where critical info crosses arbitrary fixed boundaries

### When overlap is wasted

- Sparse retrieval (BM25, SPLADE)
- Block- or semantically-aligned chunkers (boundaries already coherent)
- Cost-sensitive ingestion (overlap = N% more vectors + N% more embedding spend)

### Recommendation

Validate on your corpus before adding overlap. If chunker already aligns to logical boundaries (paragraphs, blocks, sentences), the marginal benefit of overlap is likely near zero.

---

## Implications for this project

Step 2 chunker uses **block-aware accumulation with sentence fallback** (PyMuPDF `get_text("blocks")` → split oversized at sentence boundaries → greedy pack ≤ `CHUNK_SIZE`).

| Decision | Value | Rationale |
|---|---|---|
| `CHUNK_SIZE` | **1024 chars (~256 tokens)** | Lower end of 256–512 token consensus; fits OpenAI `text-embedding-3-small` (8191-token context) comfortably; matches factoid-leaning RAG use case |
| Overlap | **None** | Block + sentence boundary alignment already provides semantic coherence; Jan 2026 evidence shows overlap adds cost without recall benefit in our retrieval setup |
| Future re-evaluation | After end-to-end eval set exists | If recall on multi-hop / analytical queries underperforms, test 512–768 token chunks and/or 10–15% overlap |

Sample-PDF distribution at `CHUNK_SIZE=1024`:

- 1310 chunks total
- avg 836 chars (~209 tokens); max 1024; min 27
- 72% land in 768–1024 chars (near upper bound, as expected for block-packing)

---

## Sources

- [Best Chunking Strategies for RAG (and LLMs) in 2026 — Firecrawl](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [RAG Chunking Strategies: The 2026 Benchmark Guide — PremAI](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/)
- [Building Production RAG Systems in 2026 — Likhon](https://brlikhon.engineer/blog/building-production-rag-systems-in-2026-complete-architecture-guide)
- [Comparative Evaluation of Advanced Chunking for RAG — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12649634/)
- [Document Chunking for RAG: 9 Strategies Tested — LangCopilot](https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide)
- [Evaluating the Ideal Chunk Size for RAG — LlamaIndex](https://www.llamaindex.ai/blog/evaluating-the-ideal-chunk-size-for-a-rag-system-using-llamaindex-6207e5d3fec5)
