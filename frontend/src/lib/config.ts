// Single source of the API base. Relative `/api` works in both dev (Next
// rewrites, next.config.ts) and prod (the Next server applies the same rewrite,
// same origin) — no absolute URL is ever baked into the client bundle.
// (Shaping D8/F1.) NEXT_PUBLIC_ exposes it to client components.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
