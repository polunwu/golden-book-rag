---
shaping: true
---

# Step 15 — Auth gate + guest mode — Shaping

## Context

The API has **zero auth** today — every endpoint in `api/routers/books.py` is
open. Deploying as-is means anyone reaching the host can upload PDFs (disk write
+ ingest), delete books, and loop `/ask` (real Gemini spend on every call).

Goal: a deployable app with a **guest mode** (browse / search / try Ask, but Ask
capped per day, no writes) and an **owner** who unlocks writes via a secret.
Owner auth starts as a single admin secret but the mechanism must be replaceable.

---

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | Deployed app must not let an unauthenticated caller write (upload / re-upload / delete) or run unbounded Gemini spend | Core goal |
| R1 | Owner unlocks privileged write operations (upload, re-upload, delete) by presenting a credential; a missing/wrong credential is rejected with a clear status | Must-have |
| R2 | Guests (no credential) can still browse the library, view a book + chunks, search, and use Ask | Must-have |
| R3 | 🟡 Every guest endpoint that spends Gemini — **Ask** (incl. `?retrieve=false`) **and Search** — is capped per day; over the cap returns **429 before any Gemini call** (no embed, no generation). Ask and Search have separate caps (different cost profiles) | Must-have |
| R4 | Auth mechanism must be **replaceable**: backend verification isolated to a single dependency seam (routers only declare `Depends(...)`), frontend credential attached at the single `request()` wrapper. Swapping secret → login touches only those two seams, not routers or call sites | Must-have |
| R5 | 🟡 Owner is not capped (Ask or Search) | Must-have |
| R6 | Secret is env-based — never baked into the client bundle, never committed | Must-have |
| R7 | 🟡 **Decided:** the enforced cap is a **single global pool shared by all guests** (owner excluded). An anonymous cookie still identifies each guest for per-guest record-keeping and to enable a future per-guest cap without re-architecting | Decided — C4-C enforced + C4-A cookie for record |

---

## CURRENT: No auth

| Part | Mechanism |
|------|-----------|
| — | All routes open. `get_conn` is the only dependency. No notion of caller identity. `/ask` and `?retrieve=false` call Gemini with no gate beyond `ASK_SCORE_FLOOR`. |

Baseline for the fit check — fails R0, R1, R3.

---

## A: Single admin secret + Postgres-backed guest Ask cap

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Owner gate (backend seam)** | |
| A1.1 | `api/auth.py:require_owner` FastAPI dependency: reads `Authorization: Bearer <secret>` (or `X-Admin-Secret`), constant-time compares to env `ADMIN_SECRET`. Missing → 401; wrong → 403 | |
| A1.2 | Apply `Depends(require_owner)` to `upload_book` and `delete_book` only. Read + search + ask routes stay open. Routers gain one dependency arg, no inline auth logic | |
| **A2** | **Identity dependency (the swap seam)** | |
| A2.1 | `api/auth.py:get_caller` dependency returns a small `Caller` object (`is_owner: bool`, `guest_id: str`). Today it derives `is_owner` from the secret check and `guest_id` from C4. Later a login system replaces this dependency's body only | |
| A2.2 | `require_owner` is defined as `get_caller` + assert `is_owner` — so there is exactly one place that knows how identity is established | |
| **A3** | **Frontend admin unlock (frontend seam)** | |
| A3.1 | `src/lib/session.ts`: read/write the secret in `localStorage` (`bookrag.adminSecret`); `isUnlocked()` predicate | |
| A3.2 | `client.ts request()` attaches `Authorization: Bearer <secret>` when present — the single attach point already anticipated in its comment | |
| A3.3 | An "Unlock" affordance (header button → dialog asking for the secret; stores it). A "Lock" / clear to drop it. Wrong secret surfaces the 403 from `request()` | |
| A3.4 | Write UI (upload dialog trigger, delete button) is shown/enabled only when `isUnlocked()`; guests see read-only surfaces | |
| **A4** | **Guest daily cap (backend)** | |
| A4.1 | `ask_usage` table: `(bucket TEXT, day DATE, count INT, PRIMARY KEY (bucket, day))`. `bucket` is the counter name, not a user — `'global:ask'` / `'global:search'` are the **enforced** rows; `'guest:<cookie_id>:ask'` etc. are per-guest **record** rows. Alembic migration (hand-written raw SQL, per repo convention) | |
| A4.2 | `services/rate_limit.py:check_and_increment(conn, bucket, limit) -> Remaining`: `INSERT ... ON CONFLICT (bucket, day) DO UPDATE SET count = count + 1 RETURNING count`, compare to `limit`. One atomic statement per bucket, no read-modify-write race | |
| A4.3 | `enforce_guest_quota(conn, caller, kind)` helper: if `caller.is_owner` → no-op (R5). Else increment the per-guest record bucket **and** the enforced `global:<kind>` bucket in one transaction; if the global count exceeds env `ASK_DAILY_LIMIT` / `SEARCH_DAILY_LIMIT` raise `HTTPException(429)` with an `X-RateLimit-Remaining` header. Called **before** `embed_query` in both `ask_book` (kind=`ask`, covers `?retrieve=false`) and `search_book` (kind=`search`) | |
| A4.4 | Anonymous guest cookie: `get_caller` reads `bookrag_gid` cookie; if absent, mints a uuid and sets it (`Set-Cookie`, `SameSite=Lax`, long-lived). This is the `guest_id` used for record buckets — not the enforced unit | |
| **A5** | **Guest cap surfaced in UI** | |
| A5.1 | On a 429 from Ask/Search, `request()` throws `ApiError(429, …)`; AskPanel renders a distinct "daily limit reached — try again tomorrow" state, separate from a content refusal | |
| A5.2 | Successful Ask/Search responses carry `X-RateLimit-Remaining` (global pool); AskPanel optionally shows "N questions left today" so guests aren't surprised by the 429 | |

**Flag note:** no ⚠️ — every part has a concrete mechanism. The one genuinely
open choice is C4 (counting unit), handled as a component decision below, plus
one contract question (429 vs refusal body) noted under Open Questions.

---

## C4: Guest counting unit (resolves R7) — DECIDED: C4-C enforced + C4-A cookie for record

Who counts as "one guest" for the daily cap?

| Req | Requirement | Status | C4-A cookie session | C4-B IP | C4-C global pool |
|-----|-------------|--------|:---:|:---:|:---:|
| R3 | Cap applied per day before any Gemini call | Must-have | ✅ | ✅ | ✅ |
| R3a | Two people behind one NAT/office IP are not lumped together | Nice-to-have | ✅ | ❌ | ❌ |
| R3b | Cannot trivially reset quota to get unlimited Gemini spend | Nice-to-have | ❌ | ✅ | ✅ |
| R3c | Works correctly behind a cloud reverse proxy without extra config | Nice-to-have | ✅ | ❌ | ✅ |

**Decision:** the **enforced** cap is **C4-C — one global daily pool shared by all
guests** (owner excluded). This gives the hardest cost ceiling against a sneaky
attacker, which is the stated fear. An anonymous **C4-A cookie** (`bookrag_gid`)
is still issued so usage is recorded per guest (`guest:<id>:*` buckets) and a
future per-guest cap can be layered on without re-architecting — but the cookie
does **not** grant each guest their own quota today.

**Notes (for the record):**
- **C4-A (cookie session):** best UX, NAT-safe, proxy-safe — but clearing cookies
  / incognito resets quota. Used here only for per-guest *record*, not enforcement.
- **C4-B (IP):** hardest to reset but NAT users share a quota and needs correct
  `X-Forwarded-For` parsing behind a proxy. Not chosen.
- **C4-C (global pool):** simplest, hardest cost ceiling; a single guest can
  exhaust everyone's quota — accepted, since capping total Gemini spend is the goal.

---

## Fit Check

| Req | Requirement | Status | CURRENT | A |
|-----|-------------|--------|:---:|:---:|
| R0 | Unauthenticated caller cannot write or run unbounded Gemini spend | Core goal | ❌ | ✅ |
| R1 | Owner unlocks writes via credential; missing/wrong rejected with clear status | Must-have | ❌ | ✅ |
| R2 | Guests can browse, view, search, and use Ask | Must-have | ✅ | ✅ |
| R3 | 🟡 Guest Ask + Search capped per day (global pool), 429 before any Gemini call | Must-have | ❌ | ✅ |
| R4 | Auth mechanism replaceable via single backend + frontend seam | Must-have | ❌ | ✅ |
| R5 | 🟡 Owner is not capped (Ask or Search) | Must-have | ❌ | ✅ |
| R6 | Secret env-based, never in client bundle / committed | Must-have | ❌ | ✅ |

**Notes:**
- CURRENT fails everything but R2 — no identity concept at all.
- A satisfies R4 by construction: A2 (`get_caller`) is the only place identity is
  established on the backend; A3.2 (`request()`) the only place a credential is
  attached on the frontend. A login migration rewrites those two bodies.
- R7 (counting unit) is parked in C4 — A passes regardless of which C4 is picked.

---

## Decisions (resolved)

1. **Counting unit** — enforced cap is a **global daily pool** shared by all
   guests (owner excluded); an anonymous cookie records per-guest usage and keeps
   a future per-guest cap cheap. (C4-C enforced + C4-A cookie.)
2. **Over-limit contract** — **429** with an `X-RateLimit-Remaining` header, so the
   limit is machine-distinguishable from a content refusal (`refused=True`).
3. **Search is capped too** — separate `SEARCH_DAILY_LIMIT` global pool, same
   429 mechanism, to blunt a sneaky embedding-spam attack.

---

## Next

Breadboard A (UI + non-UI affordances + wiring) and slice. Likely slices:
- **V1** — owner gate + FE unlock (upload/delete protected; secret header end-to-end).
- **V2** — guest daily cap (Ask + Search global pools, 429, cookie record) + UI surfacing.
