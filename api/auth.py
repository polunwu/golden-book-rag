"""Caller identity + the admin write-gate.

This is the single backend seam where identity is established. Today an admin is
whoever presents the shared `ADMIN_SECRET` as a Bearer token; everyone else is a
guest. Swapping the secret for a login system rewrites `get_caller`'s body only —
routers just declare `Depends(require_admin)` / `Depends(get_caller)`.
"""
import hmac
import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False so we own the missing-vs-wrong split (401 vs 403); it also
# emits the OpenAPI bearer scheme, giving /docs an Authorize button on gated routes.
bearer = HTTPBearer(auto_error=False)


@dataclass
class Caller:
    is_admin: bool
    # guest_id (anonymous cookie) arrives in V2 with the daily cap.


def _admin_secret() -> str:
    # Read at call time so tests' monkeypatch.setenv takes effect.
    return os.environ.get("ADMIN_SECRET", "")


def get_caller(
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
    return Caller(is_admin=is_admin)


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
