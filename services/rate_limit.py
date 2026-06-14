"""Guest daily cap for the Gemini-spending routes (Ask, Search).

The enforced unit is a **single global daily pool per kind** shared by all guests
(admin excluded); an anonymous per-guest bucket is also bumped for record-keeping
so a future per-guest cap is cheap. Counts live in `ask_usage(bucket, day)`.

`enforce_guest_quota` is called by the routers **before** any `embed_query`, so an
over-cap request spends no Gemini.
"""
import os
from datetime import UTC, date, datetime
from typing import Protocol

import psycopg
from fastapi import HTTPException
from psycopg.rows import DictRow

# Demo abuse-ceiling, not a traffic allowance (the owner demos in admin mode,
# uncapped). Overridable per deploy via env, read at call time.
_DEFAULTS = {"ask": 50, "search": 50}


class Caller(Protocol):
    """Structural view of the caller — kept here so the service layer doesn't
    import from `api.*`. `api.auth.Caller` satisfies it."""

    is_admin: bool
    guest_id: str


def _daily_limit(kind: str) -> int:
    return int(os.environ.get(f"{kind.upper()}_DAILY_LIMIT", _DEFAULTS[kind]))


def check_and_increment(
    conn: psycopg.Connection[DictRow], bucket: str, day: date
) -> int:
    """Atomically bump the (bucket, day) counter and return the new count. One
    statement — no read-modify-write race between concurrent requests."""
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
    """Admin → no-op. Else bump the per-guest record bucket and the enforced
    global bucket; if the global count exceeds the daily limit, raise 429.

    Increment-then-compare keeps each bump atomic; a blocked attempt still bumps
    the global counter (harmless — the row only grows, remaining stays at 0).
    """
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
