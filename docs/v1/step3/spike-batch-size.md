---
shaping: true
---

# Spike: Gemini `embed_content` Batch Size (B2.1)

## Context

Shape B2.1 currently sets `EMBED_BATCH_SIZE = 32` as a conservative default because
`https://ai.google.dev/gemini-api/docs/embeddings` says "doesn't specify per-request
text limits in standard mode". Picking too small wastes wall time; picking too large
breaks ingestion with cryptic errors. We need a concrete number before B6 (debug
script) runs end-to-end.

## Goal

Identify the actual per-request limits for
`client.models.embed_content(model="gemini-embedding-001", contents=...)` on the
**Gemini API** (consumer/paid tier — not Vertex AI), so `EMBED_BATCH_SIZE` can
be set with confidence and the retry path can distinguish batch-too-large from
other errors.

## Questions

| #     | Question                                                                                                            |
| ----- | ------------------------------------------------------------------------------------------------------------------- |
| Q1    | What is the maximum number of `contents` (texts) per single `embed_content` call for `gemini-embedding-001`?         |
| Q2    | Is there an aggregate token cap per request (sum of tokens across all texts), separate from the 2,048-per-text cap? |
| Q3    | What RPM / TPM rate limits apply to paid-tier Gemini API for embedding endpoints? (Drives retry backoff sizing.)     |
| Q4    | What error class / status code is returned when batch exceeds limit? (So `tenacity` can stop-retrying vs split.)     |
| Q5    | Does the official `google-genai` Python SDK auto-split oversized batches, or does it pass through unchanged?         |
| Q6    | Is the standard `embed_content` endpoint different from the Batch API in batch-size limits or pricing?               |
| Q7    | What batch sizes do official Google examples / public RAG cookbooks use for `gemini-embedding-001`?                  |

## Investigation Steps

1. Fetch primary sources:
   - `https://ai.google.dev/gemini-api/docs/embeddings` (already partly fetched)
   - `https://ai.google.dev/gemini-api/docs/rate-limits`
   - `https://ai.google.dev/gemini-api/docs/batch-mode`
   - `google-genai` Python SDK source on GitHub: `googleapis/python-genai` → search for `embed_content` request building / batch validation
2. Check official Google AI cookbook notebooks for `gemini-embedding-001` usage patterns
3. If still unclear, write a one-off probe script that calls `embed_content` with
   batches of increasing size (1, 10, 50, 100, 250) against the live API and records
   the error returned at the failure boundary

## Findings

Sources consulted: `ai.google.dev/gemini-api/docs/embeddings`,
`ai.google.dev/gemini-api/docs/rate-limits`, `ai.google.dev/gemini-api/docs/batch-mode`,
`ai.google.dev/gemini-api/docs/models`,
`docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings`,
`googleapis/python-genai` SDK source.

| #  | Answer |
| -- | ------ |
| Q1 | **Gemini API (consumer): not explicitly documented.** Docs example shows a list of 3 texts working with `gemini-embedding-001`. Vertex AI docs for the same underlying model state **250 texts/request max**. Use 250 as ceiling. |
| Q2 | **Yes — 20,000 tokens aggregate** per request per Vertex docs for the same model. Inputs exceeding this return HTTP 400. This is the binding constraint, not text count. |
| Q3 | **Not published on the docs site.** Rate-limits page redirects users to AI Studio per-project view. Only documented number: paid-tier Batch API enqueued tokens (Tier 1: 500K, Tier 2: 5M, Tier 3: 10M). |
| Q4 | **HTTP 400** on aggregate-token overrun (per Vertex docs). google-genai surfaces these as `google.genai.errors.ClientError`. Should be a **non-retryable** stop condition for `tenacity`. |
| Q5 | **No.** The `google-genai` SDK has no client-side batch validation or splitting — request is passed through as-is. `embed_chunks` must do its own splitting. |
| Q6 | Batch API supports embeddings at **50% cost** but with up to **24h turnaround** (`ai.google.dev/gemini-api/docs/batch-mode`). Not worth the complexity for a one-shot per-book MVP ingestion — stick with standard `embed_content`. Document mentions `gemini-embedding-2` rather than `-001` for Batch API; not blocking for MVP. |
| Q7 | Official Google examples (cookbook + quickstart) show batches of 3–10 texts. No reference to a recommended production batch size. |

### Key Caveat

Vertex REST API docs include the note: *"For `gemini-embedding-001`, each request can only include a single input text"* — **but this is contradicted by the Gemini API consumer docs**, which show a working multi-text example with the same model. We treat the single-text restriction as Vertex-REST-only (or stale documentation). A live probe is the only way to be certain.

## Decision

**Size batches by aggregate token count, not text count:**

- `EMBED_TOKEN_BUDGET = 18_000` per request (90% safety margin under Vertex's documented 20K cap)
- `EMBED_BATCH_HARD_CAP = 100` texts per request (well under Vertex's 250; keeps a single failure cheap to retry)
- B2.1 implementation: greedy packer that adds chunks to a batch until the next would exceed either limit, then flushes

For typical Step 2 chunks (~256 tokens each), this yields ~70 chunks per request. Roughly 6 API calls for a 400-chunk book — fast and well-bounded.

**Probe before trust:**

Before merging B6, write `scripts/probe_gemini_batch.py` that calls `embed_content` with batches of 1, 10, 50, 100 texts on a fixed sample, records latency + any errors, and confirms the SDK accepts list inputs as expected. If the "single input text" caveat turns out to apply, the probe will surface it immediately and B2.1 falls back to `EMBED_BATCH_HARD_CAP = 1`.

**Retry policy implication (B3.1):**

- Retry: `ResourceExhausted` (429), `ServiceUnavailable` (503), `DeadlineExceeded` (504), `InternalServerError` (500)
- **Do not retry:** `ClientError` HTTP 400 (batch over token cap) — these are deterministic and need a code fix, not backoff

## Acceptance

✅ Spike complete. All Q1–Q7 have either documented answers or explicit "unknown, probe required" annotations. Decision and probe plan ready to feed back into B2.1 and B3.1.
