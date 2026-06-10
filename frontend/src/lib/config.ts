// Single source of the API base. Relative `/api` works in both dev (Next
// rewrites, next.config.ts) and prod (the Next server applies the same rewrite,
// same origin) — no absolute URL is ever baked into the client bundle.
// NEXT_PUBLIC_ exposes it to client components.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

// Client-side upload cap, mirrors the backend MAX_UPLOAD_MB (api/routers/books.py)
// so we reject oversized files before the POST. Defense-in-depth, not the source
// of truth — the backend still enforces its own cap. A bad env value falls back
// to 100 rather than NaN-disabling the guard.
const maxUploadMb = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB);
export const MAX_UPLOAD_MB =
  Number.isFinite(maxUploadMb) && maxUploadMb > 0 ? maxUploadMb : 100;
