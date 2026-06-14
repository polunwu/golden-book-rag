"""Caller identity + the admin write-gate.

This is the single backend seam where identity is established. Today an admin is
whoever presents the shared `ADMIN_SECRET` as a Bearer token; everyone else is a
guest. Swapping the secret for a login system rewrites `get_caller`'s body only —
routers just declare `Depends(require_admin)` / `Depends(get_caller)`.
"""
import hmac
import os
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False so we own the missing-vs-wrong split (401 vs 403); it also
# emits the OpenAPI bearer scheme, giving /docs an Authorize button on gated routes.
bearer = HTTPBearer(auto_error=False)

# Anonymous guest id, minted by get_caller. Kept for a future per-guest cap; the
# enforced daily cap today is a global pool (see services.rate_limit), not per-guest.
GUEST_COOKIE = "bookrag_gid"
_GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # ~1 year


@dataclass
class Caller:
    is_admin: bool
    guest_id: str  # anonymous cookie id (reserved for a future per-guest cap)


def _admin_secret() -> str:
    # Read at call time so tests' monkeypatch.setenv takes effect.
    return os.environ.get("ADMIN_SECRET", "")


def get_caller(
    request: Request,
    response: Response,
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Caller:
    """The only place caller identity is established."""
    secret = _admin_secret()
    # Compare as bytes: header credentials are latin-1 decoded, so a non-ASCII
    # token would make compare_digest raise TypeError on two str.
    is_admin = bool(
        secret
        and cred is not None
        and hmac.compare_digest(
            cred.credentials.encode("utf-8"), secret.encode("utf-8")
        )
    )

    # Read-or-mint the anonymous guest id. set_cookie on the injected Response
    # propagates on routes returning a model; delete_book returns its own
    # Response so its (admin-only) caller won't carry the Set-Cookie — fine.
    gid = request.cookies.get(GUEST_COOKIE)
    if not gid:
        gid = uuid.uuid4().hex
        response.set_cookie(
            GUEST_COOKIE,
            gid,
            max_age=_GUEST_COOKIE_MAX_AGE,
            samesite="lax",
            httponly=True,
        )
    return Caller(is_admin=is_admin, guest_id=gid)


def require_admin(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    caller: Caller = Depends(get_caller),
) -> Caller:
    """Gate for write routes. Missing credential → 401, wrong → 403.

    Reads `bearer` only to tell missing from wrong; the secret comparison lives
    solely in `get_caller`. An unset/empty `ADMIN_SECRET` means nobody is admin —
    every write is rejected, but guests are still served.
    """
    if cred is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not caller.is_admin:
        raise HTTPException(status_code=403, detail="invalid credentials")
    return caller
