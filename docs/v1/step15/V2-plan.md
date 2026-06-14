---
shaping: false
---

# Step 15 V2 — Guest daily cap — Implementation Plan

Implements slice **V2** from `slices.md`. Guests share a **global daily pool**
for Gemini-spending routes (Ask + Search, separate pools); over the cap returns
**429 before any Gemini call**. Admin (V1's `is_admin`) is never capped. An
anonymous `bookrag_gid` cookie is minted so usage is also recorded per guest,
keeping a future per-guest cap cheap — but the cookie does **not** grant each
guest their own quota today (C4-C enforced + C4-A cookie for record).

Builds on V1's seam: `api/auth.py:get_caller` / `Caller`. V2 only **adds** the
`guest_id` field + cookie minting and two quota helpers; `require_admin`, the
write gates, and the FE attach point are untouched.

This slice adds a DB table → **one Alembic migration**.

---

## Backend

### Migration — `ask_usage` table (S3)

New migration (`uv run alembic revision -m "ask_usage"`), hand-written raw SQL
via `op.execute` per repo convention. `down_revision` = current head
(`6f01c766ea52`).

```python
def upgrade() -> None:
    op.execute(
        "CREATE TABLE ask_usage ("
        "  bucket TEXT NOT NULL,"
        "  day    DATE NOT NULL,"
        "  count  INT  NOT NULL DEFAULT 0,"
        "  PRIMARY KEY (bucket, day)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ask_usage")
```

`bucket` is a **counter name, not a user**: `global:ask` / `global:search` are the
**enforced** rows; `guest:<gid>:ask` / `guest:<gid>:search` are **record-only**.
Composite PK `(bucket, day)` is what the atomic upsert conflicts on. Run
`make db-migrate` after creating it (and before `make test`).

### `services/rate_limit.py` (new) — N43, N44

```python
import os
from datetime import UTC, datetime

import psycopg
from fastapi import HTTPException
from psycopg.rows import DictRow

from api.auth import Caller

_DEFAULTS = {"ask": 50, "search": 50}  # demo abuse-ceiling; deploy-tunable, see Env


def _daily_limit(kind: str) -> int:
    return int(os.environ.get(f"{kind.upper()}_DAILY_LIMIT", _DEFAULTS[kind]))


def check_and_increment(
    conn: psycopg.Connection[DictRow], bucket: str, day
) -> int:
    """Atomic per-(bucket, day) counter. One statement, no read-modify-write
    race. Returns the new count."""
    row = conn.execute(
        "INSERT INTO ask_usage (bucket, day, count) VALUES (%s, %s, 1) "
        "ON CONFLICT (bucket, day) DO UPDATE SET count = ask_usage.count + 1 "
        "RETURNING count",
        (bucket, day),
    ).fetchone()
    assert row is not None
    return row["count"]


def enforce_guest_quota(
    conn: psycopg.Connection[DictRow], caller: Caller, kind: str
) -> None:
    """Admin → no-op (R5). Else bump the per-guest record bucket **and** the
    enforced global bucket in one transaction; if the global count exceeds the
    daily limit, raise 429 — called BEFORE embed_query so no Gemini is spent."""
    if caller.is_admin:
        return
    today = datetime.now(tz=UTC).date()  # cap is per UTC day
    limit = _daily_limit(kind)

    check_and_increment(conn, f"guest:{caller.guest_id}:{kind}", today)  # record
    count = check_and_increment(conn, f"global:{kind}", today)           # enforced
    conn.commit()

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="daily limit reached — try again tomorrow",
            headers={"X-RateLimit-Remaining": "0"},
        )
```

Notes:
- **Increment-then-compare** (not check-then-increment) keeps it a single atomic
  statement per bucket. A blocked attempt still bumps the global counter past the
  limit — harmless (the row only grows; remaining stays clamped at 0).
- `limit=N` allows exactly N calls: the Nth makes `count==N` (`N > N` false →
  served); the N+1th makes `count==N+1` → 429.
- `conn.commit()` persists the counts before the handler continues to embed/search
  (which run their own reads on the same pooled connection).
- Bucket names are SQL **values** (`%s`), never identifiers — no `psycopg.sql`
  needed; the table/column names are static.

### `api/auth.py` — extend the seam (N41 cookie + `guest_id`)

`Caller` gains `guest_id`; `get_caller` reads-or-mints the `bookrag_gid` cookie.
Cookie work is browser-only (no DB) — it stays in this one dependency.

```python
import uuid
from fastapi import Request, Response  # added

GUEST_COOKIE = "bookrag_gid"


@dataclass
class Caller:
    is_admin: bool
    guest_id: str          # anonymous cookie id (record bucket); "" for admin-only paths is fine


def get_caller(
    request: Request,
    response: Response,
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Caller:
    """The only place caller identity is established."""
    secret = _admin_secret()
    is_admin = bool(
        secret and cred is not None
        and hmac.compare_digest(
            cred.credentials.encode("utf-8"), secret.encode("utf-8")
        )
    )
    gid = request.cookies.get(GUEST_COOKIE)
    if not gid:
        gid = uuid.uuid4().hex
        response.set_cookie(
            GUEST_COOKIE, gid,
            max_age=60 * 60 * 24 * 365,   # ~1y, long-lived
            samesite="lax",
            httponly=True,
        )
    return Caller(is_admin=is_admin, guest_id=gid)
```

Notes:
- `require_admin` is unchanged — it still `Depends(get_caller)`; the extra params
  are injected by FastAPI. Admin requests also mint a cookie (harmless).
- **`response.set_cookie` propagates** on routes that return a Pydantic model
  (FastAPI reuses the injected `Response`). `delete_book` returns its **own**
  `Response(status_code=204)`, so an admin's first delete won't carry the
  Set-Cookie — irrelevant (delete is admin-only; admins aren't counted).

### `api/routers/books.py` — wire the quota (N47, N48)

Add `caller = Depends(get_caller)` to `ask_book` and `search_book`, and call
`enforce_guest_quota` **before** `embed_query` in both — and, in ask, **before
the `retrieve=false` branch** (that path still spends Gemini via
`generate_plain_answer`).

```python
from api.auth import Caller, get_caller, require_admin   # + get_caller
from services.rate_limit import enforce_guest_quota

@router.post("/{book_id}/ask", response_model=AskResponse)
def ask_book(
    book_id: UUID,
    body: AskRequest,
    retrieve: bool = Query(True),
    conn: ... = Depends(get_conn),
    caller: Caller = Depends(get_caller),
) -> AskResponse:
    row = conn.execute("SELECT status FROM books WHERE id = %s", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="book not found")

    enforce_guest_quota(conn, caller, "ask")   # before BOTH gemini paths

    if not retrieve:
        ...
```

```python
@router.post("/{book_id}/search", response_model=SearchResponse)
def search_book(
    book_id: UUID,
    body: SearchRequest,
    conn: ... = Depends(get_conn),
    caller: Caller = Depends(get_caller),
) -> SearchResponse:
    # 404 / 409 ready-gate first (cheap, no Gemini), then quota, then embed:
    ...
    enforce_guest_quota(conn, caller, "search")
    query_vec = embed_query(body.query)
    ...
```

Ordering rationale: keep the existing 404 / 409 checks first (they're free and
report a clearer error), then the quota gate, then `embed_query`. The quota still
precedes every Gemini call. `list/get/chunks/upload/delete` are untouched.

### Env (S2)

Add to `.env` and `.env.example` (read at call time):

```
ASK_DAILY_LIMIT=50
SEARCH_DAILY_LIMIT=50
```

Both 50: this is a demo, so the cap is a **bot / crawler ceiling**, not a traffic
allowance. The owner demos in admin mode (uncapped, R5), so the pool is only ever
spent by un-unlocked visitors — a script hammering it costs ~$0.1/day at most.
Defaults live in `rate_limit._DEFAULTS` so an unconfigured deploy still caps;
tighten via `.env` (call-time read) without touching code.

---

## Frontend

### `src/api/client.ts` — friendly 429 (N25)

Add one case to `ApiError.friendly`:

```ts
case 429:
  return "You've reached today's question limit. Try again tomorrow.";
```

`ApiError.status` is already public, so AskPanel can branch on it.

### `src/components/books/AskPanel.tsx` — limit state (U12 / N31)

The ask mutation already rejects on a non-2xx. Distinguish the 429 from a generic
error and from a content refusal:

```tsx
import { ApiError } from "@/api/client";

const limitReached =
  mutation.error instanceof ApiError && mutation.error.status === 429;
```

Render a calm, distinct surface when `limitReached` (reuse `Notice`, not the red
`ErrorState`) instead of the generic error block:

```tsx
{mutation.error &&
  (limitReached ? (
    <Notice className="mt-6">
      You&rsquo;ve reached today&rsquo;s question limit. Try again tomorrow.
    </Notice>
  ) : (
    <div className="mt-6">
      <ErrorState detail={(mutation.error as Error).message} />
    </div>
  ))}
```

The limit is a benign shared-quota state, not a failure — `Notice` (the same
component the not-ready banner uses) reads correctly; red would overstate it.
This is the **only required** FE change (no Search UI exists, so N48 has no FE
surface — backend-only).

### Optional — "N left today" (U13 / N25h), deferred

`request()` returns the parsed body only; surfacing `X-RateLimit-Remaining`
means either threading response headers out of the wrapper or a small
`GET /usage` endpoint. Out of scope for the must-ship; the 429 state stands
alone. If added later: set the header on the success path too (inject
`response: Response` into the handler) and read it through a widened wrapper.

---

## Tests

Gemini stays stubbed (conftest). The global pool is a **real shared table**, so
without isolation the session's counts accumulate and break the existing
ask/search tests. Add an autouse reset fixture to `conftest.py`:

```python
@pytest.fixture(autouse=True)
def _reset_usage() -> None:
    """Each test starts with empty quota counters (global pool is shared
    cross-test in the real DB)."""
    with get_pool().connection() as conn:
        conn.execute("TRUNCATE ask_usage")
        conn.commit()
```

> Note: `ask_usage` must exist → this needs the migration applied. It also means
> existing guest ask/search tests keep passing as long as a single test stays
> under the per-test default limit (it does).

New `tests/test_rate_limit.py`. Set low limits per-test via
`monkeypatch.setenv("ASK_DAILY_LIMIT", "2")` etc. (read at call time). Reuse the
`_ready_book` pattern from `test_ask.py` (synchronous — TestClient runs the
ingest BackgroundTask inline).

- **Guest cap enforced:** with `ASK_DAILY_LIMIT=2`, two guest asks → 200; the
  third → **429** with `detail` "daily limit reached…" and header
  `X-RateLimit-Remaining: 0`.
- **No Gemini past the cap:** spy `books_mod.embed_query` (wrap the conftest stub
  with a call counter); assert the counter does **not** advance on the 429 call
  (quota precedes embed). Same for the `retrieve=false` path (assert
  `generate_plain_answer` not called when over cap).
- **Admin uncapped (R5):** same low limit, requests with `ADMIN_HEADERS` past the
  cap all return 200.
- **Separate pools:** exhausting `ask` does not 429 `search`, and vice versa.
- **Cookie minted (S4):** first guest request → response sets `bookrag_gid`;
  reusing the cookie keeps the same `guest_id` (assert `Set-Cookie` present, and a
  `guest:<gid>:ask` row exists in `ask_usage`).
- **Record vs enforced rows:** after guest asks, both `global:ask` and exactly one
  `guest:*:ask` row exist with the expected counts.

`book_ids` teardown still DELETE-CASCADEs created books; `_reset_usage` handles
the usage table.

---

## Manual verification

1. `make db-migrate` (apply `ask_usage`), `make api-dev` + `make web`, with
   `ASK_DAILY_LIMIT`/`SEARCH_DAILY_LIMIT` set low (e.g. 2) in `.env` to see it fast.
2. As **guest** on a ready book: ask twice → answers; third ask → AskPanel shows
   the calm "daily limit reached" `Notice`, **not** a red error. Confirm in the
   network tab the third request is **429** and no Gemini latency (instant).
3. Unlock at `/auth` (V1) → **admin**: asking past the cap keeps working (R5).
4. `curl` `POST /books/{id}/search` past `SEARCH_DAILY_LIMIT` as guest → 429,
   independent of the ask pool.
5. Inspect cookies: `bookrag_gid` is set on the first guest request and reused.
6. `psql` (`make db-shell`): `SELECT * FROM ask_usage;` shows `global:ask`
   (enforced) and `guest:<id>:ask` (record) rows.

---

## Out of scope (V2)

- Per-guest **enforcement** (today the cookie only records; the global pool gates) —
  the table/bucket shape already supports layering it on later (R7).
- "N left today" counter (U13/N25h) — optional, deferred above.
- Surfacing the Search cap in the UI — no Search screen exists.
- Gating `/docs` / `/openapi.json`, and any per-route 429 OpenAPI documentation.
- Day-rollover / timezone edge tests (cap is per UTC day; not exercised).
