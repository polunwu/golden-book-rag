---
shaping: true
---

# Step 8: V1 Implementation Plan — Frontend Foundation

Implements **V1** from [slices.md](./slices.md) — all of Shape A: the `frontend/`
Next.js (App Router) scaffold + shell (A1), env + Next dev rewrites (A2),
OpenAPI→zod codegen (A3), the hand-written typed client + `ApiError` (A4),
`listBooks` (A5), TanStack Query (A6), the connectivity-smoke route (A7), shared
primitives (A8), and repo wiring (A9).

Demo: `make api` + `cd frontend && yarn dev` → `/` shows **"Connected · N books"**
from `GET /books` through the typed client + generated zod; backend down → error
state; `/books/[id]` → placeholder in the shell.

**No backend changes** (D2/D8 — origin via the Next.js dev rewrite). New
top-level `frontend/` only, plus two root files (`Makefile`, `.gitignore`).

**Framework note (D1):** Next.js App Router is chosen because **auth is almost
certainly coming** — App Router gives the httpOnly-cookie session, `middleware.ts`
route protection, and server-component session-read seams a static SPA lacks
(see shaping D1/D9, C0.6). Step 8 builds **none** of that; the MVP screens are
client components using TanStack Query. The seam is reserved, not exercised.

## Files

| File                                          | Action |
|-----------------------------------------------|--------|
| `frontend/` (scaffold)                        | Create — `create-next-app` (App Router, TS, Tailwind, `src/`) + TanStack Query + zod + openapi-zod-client (A1) |
| `frontend/next.config.ts`                     | `async rewrites()` `/api/:path*` → `:8000/:path*` (A2/N4) |
| `frontend/.env.example`                       | `NEXT_PUBLIC_API_BASE_URL=/api` (A2/S2) |
| `frontend/src/lib/config.ts`                  | `API_BASE_URL` reader (A2/N3) |
| `frontend/src/api/client.ts`                  | `request<T>` + `ApiError` (A4/N5, N6) |
| `frontend/src/api/books.ts`                   | `listBooks()` (A5/N7) |
| `frontend/src/api/generated/schemas.ts`       | Generated, committed (A3/S1) |
| `frontend/schemas-only.hbs`                   | openapi-zod-client template — schemas only, no Zodios (A3) |
| `frontend/src/app/layout.tsx`                 | Root shell + nav + `{children}` + `<Providers>` (A1/U4, U5, N1) |
| `frontend/src/app/providers.tsx`              | `"use client"` `QueryClientProvider` boundary (A6/N2) |
| `frontend/src/components/Loading.tsx`         | Shared primitive (A8/U2) |
| `frontend/src/components/ErrorState.tsx`      | Shared primitive (A8/U3) |
| `frontend/src/components/Empty.tsx`           | Shared primitive (A8/U7) |
| `frontend/src/app/page.tsx`                   | Smoke (A7/U1, N8) — `"use client"` |
| `frontend/src/app/books/[id]/page.tsx`        | Placeholder (A1/U6) |
| `frontend/src/app/robots.ts`                  | `Disallow: /` — non-indexed app (A1/D10) |
| `frontend/src/app/globals.css`                | `@import "tailwindcss";` (v4) |
| `Makefile`                                    | `openapi`, `web` targets (A9/N10) |
| `.gitignore`                                  | frontend ignores + `.env.example` un-ignore (A9) |

---

## 0. Scaffold (A1)

From the repo root:

```bash
yarn create next-app frontend --ts --app --tailwind --src-dir --eslint --import-alias "@/*" --use-yarn
cd frontend
yarn add @tanstack/react-query zod
yarn add -D openapi-zod-client
```

`create-next-app --tailwind` wires Tailwind v4 (current) via `@tailwindcss/postcss`
and a `globals.css` that already starts with `@import "tailwindcss";` — no
`tailwind.config.js`, no manual PostCSS. `--src-dir` puts the app under `src/`
(`src/app/…`), keeping paths close to the rest of the plan; create-next-app also
configures the `@/*` import alias (→ `./src/*`). **This plan uses plain relative
imports** (`../lib/config`) so every path below is literal and copy-pasteable; the
`@/*` alias works too if you prefer it. (Accept defaults for any remaining
interactive prompts, e.g. Turbopack — they don't affect this plan.)

Delete the create-next-app demo boilerplate inside `src/app/page.tsx` (replaced
in §6) and any starter assets; keep `globals.css` (Tailwind import) and the
generated `layout.tsx` (replaced in §5).

---

## 1. Env + Next rewrites (A2 — N3, N4, S2)

`frontend/src/lib/config.ts`:

```ts
// Single source of the API base. Relative `/api` works in both dev (Next
// rewrites, next.config.ts) and prod (the Next server applies the same rewrite,
// same origin) — no absolute URL is ever baked into the client bundle.
// (Shaping D8/F1.) NEXT_PUBLIC_ exposes it to client components.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
```

`frontend/next.config.ts`:

```ts
import type { NextConfig } from "next";

// Dev origin (D8/G1-A): the browser only ever talks to the Next origin; Next
// rewrites /api/* to the backend, stripping the /api prefix (backend routes are
// /books, not /api/books). No CORS, backend untouched. The same rewrite runs on
// the Next server in prod (single origin). The backend target is env-overridable
// for non-local deploys; defaults to the dev backend.
const BACKEND = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/:path*` }];
  },
};

export default nextConfig;
```

`frontend/.env.example`:

```
NEXT_PUBLIC_API_BASE_URL=/api
```

---

## 2. OpenAPI → zod codegen (A3 — N10, N11, S1)

Goal: generate **pure zod schemas** from the backend OpenAPI — no Zodios/axios
client (D3/D6). `openapi-zod-client` emits a Zodios client by default, so pass a
**schemas-only Handlebars template**.

`frontend/schemas-only.hbs`:

```handlebars
import { z } from "zod";

{{#each schemas}}
export const {{@key}} = {{{this}}};
export type {{@key}} = z.infer<typeof {{@key}}>;
{{/each}}
```

`frontend/package.json` — add the `gen:api` script (create-next-app already
provides `dev`/`build`/`start`/`lint`):

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "gen:api": "openapi-zod-client openapi.json -o src/api/generated/schemas.ts -t schemas-only.hbs --export-schemas"
  }
}
```

The `openapi.json` is dumped by the root `Makefile` (§7) so codegen is offline +
reproducible (R3.3). The generated `src/api/generated/schemas.ts` is **committed**
(F3) — drift shows as a diff. Generated names mirror the backend component
schemas: `BookOut`, `ChunkBase`, `Citation`, `SearchHit`, `AskResponse`, and the
`GET /books` response model `BookList` (`{ items: BookOut[] }`).

> Implementation note: confirm the generated export names against the dumped
> `openapi.json` (`components.schemas` keys). If FastAPI emits a suffixed name
> (e.g. `BookList-Output`), openapi-zod-client sanitizes it — adjust the import in
> `books.ts` (§4) to the actual generated identifier. This is the only step whose
> exact symbol names depend on generator output; everything else is fixed.

---

## 3. Typed client + `ApiError` (A4 — N5, N6)

`frontend/src/api/client.ts`:

```ts
import type { z } from "zod";
import { API_BASE_URL } from "../lib/config";

// N6 — typed error: backend returns { detail: string }; map status + detail to a
// friendly message (shaping R2.2). `message` (Error.message) is what TanStack
// Query surfaces; `detail`/`status` stay available for richer UI later.
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(ApiError.friendly(status, detail));
    this.name = "ApiError";
  }

  static friendly(status: number, detail: string): string {
    switch (status) {
      case 404:
        return "Not found.";
      case 409:
        return "This book isn't ready yet.";
      case 413:
        return "That file is too large.";
      case 422:
        return detail || "Invalid request.";
      default:
        return detail || `Request failed (${status}).`;
    }
  }
}

// N5 — the one fetch wrapper. Base URL from config, JSON in/out, zod-parse on
// success, throw ApiError on non-2xx or shape mismatch. No axios (D6). Works
// from client components today; the same wrapper is where a session header /
// cookie pass-through lands when auth arrives (D1/D9).
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }

  const parsed = schema.safeParse(await res.json());
  if (!parsed.success) {
    // Backend drift / unexpected shape — surface, don't return a silent `any`.
    throw new ApiError(res.status, `Unexpected response shape: ${parsed.error.message}`);
  }
  return parsed.data;
}
```

---

## 4. `listBooks` (A5 — N7)

`frontend/src/api/books.ts`:

```ts
import { request } from "./client";
import { BookList, type BookOut } from "./generated/schemas";

// N7 — the only endpoint wired this step (R2.3). Adding more (getBook, ask, …)
// is a one-liner against `request` in their own steps.
export async function listBooks(): Promise<BookOut[]> {
  const data = await request("/books", BookList);
  return data.items;
}

export type { BookOut };
```

---

## 5. App shell + providers + routes (A1, A6 — N1, N2, U4–U6)

`frontend/src/app/providers.tsx` (the `"use client"` boundary that lets the
server-rendered layout mount TanStack Query):

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

// N2 — one QueryClient per browser session. useState (not a module singleton) so
// each client gets its own instance and it survives re-renders. Mounted in the
// root layout (§ below).
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```

`frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "./providers";
import "./globals.css";

// D10 — non-indexed app-wide: robots noindex/nofollow propagates to every route
// from the root layout. Cheap crawler deterrent, NOT access control (auth is the
// real gate). Paired with app/robots.ts (§ below).
export const metadata: Metadata = {
  title: "golden-book-rag",
  robots: { index: false, follow: false },
};

// N1 — root layout: chrome (header/nav) + the App Router <Outlet> equivalent
// ({children}), wrapped in the client Providers boundary. Every route nests here.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-50 text-zinc-900">
        <Providers>
          <header className="border-b bg-white">
            <nav className="mx-auto flex max-w-3xl items-center px-4 py-3">
              <Link href="/" className="font-semibold">
                golden-book-rag
              </Link>
            </nav>
          </header>
          <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
```

`frontend/src/app/books/[id]/page.tsx`:

```tsx
// Placeholder route (Step 10+). Registered now so the shell + routing are real.
// Server component; params is a Promise in the App Router.
export default async function BookDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <p className="text-sm text-zinc-500">Book {id} — coming soon.</p>;
}
```

`frontend/src/app/robots.ts` (D10 — `Disallow: /` for all crawlers; Next serves
this as `/robots.txt`):

```ts
import type { MetadataRoute } from "next";

// D10 — keep the app out of search indexes. Polite-crawler deterrent only; the
// real privacy gate is auth (D1). Pairs with the root metadata.robots noindex.
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
```

---

## 6. Shared primitives + smoke (A8, A7 — U2, U3, U7, U1, N8)

`frontend/src/components/Loading.tsx`:

```tsx
export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="text-sm text-zinc-500">{label}</p>;
}
```

`frontend/src/components/ErrorState.tsx`:

```tsx
export function ErrorState({ detail }: { detail: string }) {
  return (
    <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {detail}
    </p>
  );
}
```

`frontend/src/components/Empty.tsx`:

```tsx
// Defined now (R4.2) for reuse in Steps 9+; the smoke doesn't render it.
export function Empty({ label = "Nothing here yet." }: { label?: string }) {
  return <p className="text-sm text-zinc-500">{label}</p>;
}
```

`frontend/src/app/page.tsx` (N8 + U1) — a client component because it uses
`useQuery`:

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { listBooks } from "../api/books";
import { Loading } from "../components/Loading";
import { ErrorState } from "../components/ErrorState";

// A7 — the connectivity smoke. Proves env → client → generated-zod → render
// end-to-end against the live backend. (No Library grid — that's Step 9.)
export default function Home() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["books"],
    queryFn: listBooks,
  });

  if (isLoading) return <Loading label="Connecting to backend…" />;
  if (error) return <ErrorState detail={(error as Error).message} />;

  const n = data!.length;
  return (
    <div className="flex items-center gap-2">
      <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" />
      <span>
        Connected · {n} book{n === 1 ? "" : "s"}
      </span>
    </div>
  );
}
```

---

## 7. Repo wiring (A9 — N10, ignores)

Append to the root `Makefile` (and add the new names to `.PHONY`):

```make
# Dump the backend OpenAPI offline (no server) and regenerate the frontend zod
# schemas. app.openapi() introspects routes; importing api.main does not open the
# DB pool (that's the lifespan, not import). (Shaping A3/R3.3.)
openapi:
	uv run python -c "import json, api.main; print(json.dumps(api.main.app.openapi()))" > frontend/openapi.json
	cd frontend && yarn gen:api

# Frontend dev server (Next.js). Run alongside `make api` (uvicorn) in another shell.
web:
	cd frontend && yarn dev
```

`.PHONY` line gains `openapi web`.

`.gitignore` — append:

```
# frontend
frontend/node_modules/
frontend/.next/
frontend/openapi.json
!frontend/.env.example
```

(`frontend/openapi.json` is the throwaway codegen input — only the generated
`schemas.ts` is committed. `frontend/.next/` is the Next build cache. The
`!frontend/.env.example` negates the existing `.env.*` rule so the example is
tracked.)

---

## Implementation Order

1. **Scaffold** (§0) — `yarn create next-app … --src-dir`, add deps, confirm the
   Tailwind `@import` is in `globals.css`, drop demo boilerplate. `yarn dev` shows
   the default Next page.
2. **Env + rewrites** (§1) — `lib/config.ts`, `next.config.ts`, `.env.example`.
3. **Codegen** (§2 + §7 `make openapi`) — boot nothing; run `make openapi` to
   produce `src/api/generated/schemas.ts`. Verify `BookList`/`BookOut` exports
   exist; fix the §4 import name if the generator sanitized it.
4. **Client** (§3) — `client.ts` (`request` + `ApiError`).
5. **Endpoint** (§4) — `books.ts` `listBooks`.
6. **Shell + providers + routes** (§5) — `providers.tsx`, `layout.tsx` (incl.
   `metadata.robots` noindex), `books/[id]/page.tsx`, `robots.ts`.
7. **Primitives + smoke** (§6) — `Loading`/`ErrorState`/`Empty`, `page.tsx`.
8. **Repo wiring** (§7) — `Makefile`, `.gitignore`.
9. **Smoke run** — `make db-up` (if needed) → `make api` in one shell, `make web`
   in another → open `/`:
   - backend up with ≥0 books → "Connected · N books"
   - stop `uvicorn`, reload → friendly error state
   - visit `/books/abc` → placeholder in the shell
10. **Build gate** — `cd frontend && yarn build` green (`next build`);
    `grep -ri "axios\|zodios" frontend/src` returns nothing (D6).

---

## Done When

- `/` renders **"Connected · N books"** with the live `GET /books` count, via
  `request` → Next rewrite → generated-zod parse → TanStack Query
- Backend down / non-2xx → `<ErrorState>` shows `ApiError.message` (friendly), no
  white screen or unhandled rejection
- A zod parse mismatch surfaces as the same error state, not a silent `any`
- The Next rewrite is the only path to the backend — no CORS added; the backend is
  untouched (`git status` shows only `frontend/`, `Makefile`, `.gitignore`)
- `/books/[id]` renders the placeholder inside the shared shell; nav renders
- `make openapi` regenerates `src/api/generated/schemas.ts` offline
  (`app.openapi()`), and the file is committed
- `yarn build` is green; no axios/Zodios dependency is pulled in
- App is non-indexed (D10): `curl localhost:3000/robots.txt` → `Disallow: /`, and
  page HTML carries `<meta name="robots" content="noindex, nofollow">`
- No auth/middleware, no feature screens, no per-endpoint fns beyond `listBooks`,
  no `impeccable` pass (Step 9+ / auth-step scope)

## Step 9 Hand-off

Carried forward (see [shaping.md](./shaping.md) "Out of Scope"):

- **Auth (post-MVP)** is the reason for the App Router (D1/D9). When it lands it
  uses seams built here: a `middleware.ts` for edge route protection, a
  server-component session read, and the `request` wrapper (N5) as the single
  place to attach the session credential. It also needs the backend owner-scoping
  change (C0.6). None of this is built in Step 8.
- **Library grid** (Step 9) is the first feature screen — it reuses `listBooks`
  (N7), the shared `<Loading>`/`<ErrorState>`/`<Empty>` primitives, and the
  TanStack Query pattern this step established. It adds status badges + cards.
- **Per-endpoint client fns** — each later step adds its `request(...)` one-liner
  (`getBook`, `getChunks`, `search`, `ask`, `uploadBook`, `deleteBook`) against
  the same wrapper + generated schemas.
- **Codegen on backend change** — re-run `make openapi` whenever a backend schema
  changes; the committed `schemas.ts` diff is the contract-drift signal.
- **`impeccable` polish** rides each feature screen, not this structural step.
- **Prod origin** is decided (D8: the Next server applies the same `/api` rewrite,
  single origin, optionally behind a deploy proxy) but built at the deploy step;
  backend CORS only if FE/BE ever split origins.
