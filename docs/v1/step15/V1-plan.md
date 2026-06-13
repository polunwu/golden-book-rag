---
shaping: false
---

# Step 15 V1 — Owner gate + `/auth` unlock — Implementation Plan

Implements slice **V1** from `slices.md`. Owner unlocks writes (upload,
re-upload, delete) with an admin secret; everyone else is a guest with read +
search + ask still open (the cap is V2). Two seams only: backend `get_caller`
(`api/auth.py`), frontend `request()` attach point.

No DB migration in V1 — there is no new table until V2.

---

## Backend

### `api/auth.py` (new)

```python
import hmac, os
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer(auto_error=False)   # N40 — we own the 401/403 split


@dataclass
class Caller:                            # A2 — the identity object
    is_owner: bool
    # guest_id added in V2 (cookie). V1 has no per-guest concept.


def _admin_secret() -> str:
    return os.environ.get("ADMIN_SECRET", "")   # read at call time (tests setenv)


def get_caller(                          # N41 — the ONLY place identity is established
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Caller:
    secret = _admin_secret()
    is_owner = bool(
        secret and cred is not None
        and hmac.compare_digest(cred.credentials, secret)
    )
    return Caller(is_owner=is_owner)


def require_owner(                        # N42 — gate; reuses get_caller
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    caller: Caller = Depends(get_caller),
) -> Caller:
    if cred is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not caller.is_owner:
        raise HTTPException(status_code=403, detail="invalid credentials")
    return caller
```

Notes:
- `hmac.compare_digest` = constant-time compare (R6 hygiene).
- `ADMIN_SECRET` **unset/empty ⇒ nobody is owner** — every write 401/403. Safe
  default for an un-configured deploy; the app still serves guests.
- `require_owner` reads `bearer` itself only to tell **missing (401)** from
  **wrong (403)**; the secret comparison lives solely in `get_caller`.

### `api/routers/books.py`

Import and apply to the two write routes only:

```python
from api.auth import require_owner, Caller

@router.post("/upload", ...)
def upload_book(..., _owner: Caller = Depends(require_owner)) -> UploadResponse:

@router.delete("/{book_id}", ...)
def delete_book(..., _owner: Caller = Depends(require_owner)) -> Response:
```

`list_books`, `get_book`, `get_chunks`, `search_book`, `ask_book` untouched in
V1. The dependency arg both enforces and (via the OpenAPI security scheme) makes
upload/delete show 🔒 + an Authorize button in `/docs`.

### Env

- `.env` + `.env.example`: add `ADMIN_SECRET=` (example: a long random string;
  `.env.example` ships a placeholder, never a real value — R6).

---

## Frontend

### `src/lib/session.ts` (new)

```ts
const KEY = "bookrag.adminSecret";
const EVT = "bookrag:auth";   // same-tab change signal

export function getSecret(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}
export function setSecret(s: string): void {
  window.localStorage.setItem(KEY, s);
  window.dispatchEvent(new Event(EVT));
}
export function clearSecret(): void {
  window.localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(EVT));
}
export function isAuthed(): boolean {
  return !!getSecret();
}
// Reactive read for components — useSyncExternalStore, SSR-safe.
export function useAuthed(): boolean {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVT, cb);        // same-tab (set/clear)
      window.addEventListener("storage", cb);  // cross-tab
      return () => {
        window.removeEventListener(EVT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    () => isAuthed(),     // client snapshot
    () => false,          // server snapshot — render as guest, hydrate to truth
  );
}
```

### `src/api/client.ts` (the attach seam, N24)

In `request()`, before `fetch`, attach the credential when present:

```ts
import { getSecret } from "@/lib/session";
// ...inside request(), after building `headers`:
const secret = getSecret();
if (secret) headers.set("authorization", `Bearer ${secret}`);
```

Single attach point — every call (FormData uploads included) gets the header.
Also add a friendly message for **401/403** in `ApiError.friendly` so a wrong
secret on a write reads clearly (e.g. 401 → "Authentication required.", 403 →
"Those credentials were rejected."). (429 lands in V2.)

### `src/app/auth/page.tsx` (new route, P2)

Client component. Branch on `useAuthed()`:
- **Guest:** an `AuthForm` (colocated) — secret `<Input>` + "Authenticate"
  `<Button>`. On submit: `setSecret(value)` then `router.replace("/")`.
- **Owner:** a short "You're in owner mode" line + "Switch to guest mode"
  `<Button>` → `clearSecret()` then `router.replace("/")`.
- Both: a "Back to library" `<Link href="/">`.

No `<Link>` anywhere else points to `/auth` (undiscoverable). Secret never enters
the URL. Inherits app-wide `noindex` from the root layout.

### Header indicator (U2/U3)

`layout.tsx` is a server component; add a small **client island**
`src/components/ui/AuthIndicator.tsx` (`"use client"`, uses `useAuthed()`):
renders "Guest mode" (muted) or "Owner mode" (emphasis). Drop it into the
existing header `<nav>`. Keep it text-only — it reports, never toggles.

### Gate the write UI

- `src/app/page.tsx` (Library): `const canWrite = useAuthed();` — render the
  "Upload book" button and the empty-state upload action only when `canWrite`;
  pass `canWrite` down so `BookCard` shows its **Re-upload** action only when true.
- `src/components/books/BookCard.tsx`: accept `canWrite?: boolean`, gate the
  re-upload trigger on it.
- `src/app/books/[id]/page.tsx`: `const canWrite = useAuthed();` — render the
  **Delete** button only when `canWrite`.

Guests see clean read-only surfaces; no disabled-button clutter.

---

## Tests (`tests/`)

Gemini stays stubbed (conftest). Add `tests/test_auth.py`:

- `ADMIN_SECRET` via `monkeypatch.setenv` (read at call time, so per-test works).
- `upload` / `delete` **no header → 401**; **wrong Bearer → 403**;
  **correct Bearer → 202 / 204**.
- `list` / `get` / `search` / `ask` **work with no header** (still open in V1).
- `ADMIN_SECRET` unset → any write → 401 (no owner possible).

Use the existing TestClient fixture; pass `headers={"Authorization": f"Bearer {secret}"}`.

---

## Manual verification

1. `make api-dev` + `make web`. With `ADMIN_SECRET` set in `.env`.
2. As guest at `/`: no Upload button; book detail has no Delete; Ask/search work.
3. Visit `/auth`, paste the secret, Authenticate → bounced to `/`, header now
   "Owner mode", Upload + Delete visible and functional.
4. Re-visit `/auth` → "Switch to guest mode" → back to read-only.
5. Paste a **wrong** secret → header flips to "Owner mode" (unverified) but the
   first upload/delete returns 403 with the friendly message. (See limitation.)
6. `/docs`: upload + delete show 🔒; Authorize with the secret → they succeed;
   read/search/ask need no auth.

---

## Out of scope (V1)

- All rate limiting, the `ask_usage` table, the `bookrag_gid` cookie, 429 UI — **V2**.
- Gating `/docs` / `/openapi.json` themselves (they stay public).
- **Optional, cheap:** a non-gated `GET /me → {is_owner}` (via `get_caller`) so
  `/auth` can verify the secret before flipping the indicator, removing the
  "wrong secret shows Owner mode" limitation. Add if the misleading indicator
  bothers in practice; not required for the V1 demo.
