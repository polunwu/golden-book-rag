---
shaping: false
---

# Step 15 — Auth gate + guest mode — Slices

Vertical increments cut from `breadboard.md`. Two slices; each ends in a
demo-able state. V2 builds on the identity seam (`get_caller`) introduced in V1.

| # | Slice | Mechanism (shape) | Demo |
|---|-------|-------------------|------|
| V1 | Admin gate + `/auth` unlock | A1, A2 (`is_admin`), A3 | Guest sees only "Guest mode" and no write UI; visit `/auth`, paste secret → "Admin mode" + upload/delete appear and work; back at `/auth` → "Switch to guest mode" → read-only again; wrong secret → write rejected 403; `/docs` shows Authorize 🔒 on upload/delete |
| V2 | Guest daily cap | A2 (cookie), A4, A5 | As guest, exhaust `ASK_DAILY_LIMIT` → next Ask shows "daily limit reached" with **no Gemini call** (429 before embed); admin unlimited; Search capped on a separate pool; `bookrag_gid` cookie minted |

---

## V1 — Admin gate + `/auth` unlock

**Affordances:** U2–U9, U14, N20–N24, N40–N42, N45–N46, S1, S5.

**What ships:**
- Backend `api/auth.py`: `HTTPBearer(auto_error=False)` (N40), `get_caller → Caller{is_admin}` (N41), `require_admin` (N42, 401 missing / 403 wrong).
- `Depends(require_admin)` on `upload_book` (N45) + `delete_book` (N46). All read/search/ask routes stay open.
- Frontend `/auth` route (P2): secret input + Authenticate (guest) / "Switch to guest mode" (admin). Undiscoverable — nothing links to it.
- `lib/session.ts` (S5 + `useAuthed`), `request()` attaches `Authorization: Bearer` (N24), header mode indicator (U2/U3), write UI gated on `useAuthed()` (U4/U5/U9).

**Demo:** the row above. The whole guest/admin split is observable end-to-end.

**Deliberately deferred to V2:** the per-guest cookie (`guest_id` stays unused in
`Caller`), all rate-limit code, the 429 UI. Read/search/ask have no cap yet in V1.

**Known V1 limitation (carried, not fixed here):** `useAuthed()` means "a secret
is present in localStorage", not "the secret is correct". A wrong secret shows
"Admin mode" in the header but writes 403. Acceptable for V1 (the breadboard's
A3.3 says wrong secret surfaces the 403). Optional hardening — a non-gated
`GET /me` returning `{is_admin}` via `get_caller` so `/auth` can confirm before
flipping the indicator — is noted in `V1-plan.md` as out-of-scope-but-cheap.

---

## V2 — Guest daily cap

**Affordances:** N25, N31, U12, U13, N41 (cookie/`guest_id`), N43–N44, N47–N48, S2, S3, S4.

**What ships:**
- Alembic migration: `ask_usage(bucket, day, count)` table (S3, hand-written raw SQL).
- `services/rate_limit.py`: `check_and_increment` (N43, atomic upsert) + `enforce_guest_quota` (N44, admin no-op; else incr guest record bucket + enforced global bucket; global over `*_DAILY_LIMIT` → 429 + `X-RateLimit-Remaining`).
- `get_caller` extended to mint/read the `bookrag_gid` cookie (S4) → `guest_id`.
- Quota call wired **before** `embed_query` in `ask_book` (N47, also before the `retrieve=false` branch) and `search_book` (N48).
- Frontend: `ApiError.friendly` adds 429 (N25); AskPanel renders the limit state (U12, N31). "N left today" (U13/N25h) optional.

**Demo:** the row above.

**Depends on V1:** reuses `Caller`/`get_caller` from `api/auth.py` unchanged —
V2 only adds the `guest_id` field and the quota helpers.
