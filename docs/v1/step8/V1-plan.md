---
shaping: true
---

# Step 8: V1 Implementation Plan — Frontend Foundation

Implements **V1** from [slices.md](./slices.md) — all of Shape A: the `frontend/`
Vite scaffold + shell (A1), env + Vite dev proxy (A2), OpenAPI→zod codegen (A3),
the hand-written typed client + `ApiError` (A4), `listBooks` (A5), TanStack Query
(A6), the connectivity-smoke route (A7), shared primitives (A8), and repo wiring
(A9).

Demo: `make api` + `cd frontend && yarn dev` → `/` shows **"Connected · N books"**
from `GET /books` through the typed client + generated zod; backend down → error
state; `/books/:id` → placeholder in the shell.

**No backend changes** (D2/D8 — origin via the Vite dev proxy). New top-level
`frontend/` only, plus two root files (`Makefile`, `.gitignore`).

## Files

| File                                          | Action |
|-----------------------------------------------|--------|
| `frontend/` (scaffold)                        | Create — Vite `react-ts` + Tailwind + react-router + TanStack Query + zod + openapi-zod-client (A1) |
| `frontend/vite.config.ts`                     | React plugin + `server.proxy` `/api` → `:8000` (A2/N4) |
| `frontend/src/vite-env.d.ts`                  | Type `import.meta.env.VITE_API_BASE_URL` |
| `frontend/.env.example`                       | `VITE_API_BASE_URL=/api` (A2/S2) |
| `frontend/src/config.ts`                      | `API_BASE_URL` reader (A2/N3) |
| `frontend/src/api/client.ts`                  | `request<T>` + `ApiError` (A4/N5, N6) |
| `frontend/src/api/books.ts`                   | `listBooks()` (A5/N7) |
| `frontend/src/api/generated/schemas.ts`       | Generated, committed (A3/S1) |
| `frontend/schemas-only.hbs`                   | openapi-zod-client template — schemas only, no Zodios (A3) |
| `frontend/src/main.tsx`                        | Bootstrap providers (A6/N1) |
| `frontend/src/router.tsx`                      | Routes (A1/N2) |
| `frontend/src/components/Layout.tsx`          | Shell + nav + `<Outlet/>` (A1/U4, U5) |
| `frontend/src/components/Loading.tsx`         | Shared primitive (A8/U2) |
| `frontend/src/components/ErrorState.tsx`      | Shared primitive (A8/U3) |
| `frontend/src/components/Empty.tsx`           | Shared primitive (A8/U7) |
| `frontend/src/routes/Home.tsx`                | Smoke (A7/U1, N8) |
| `frontend/src/routes/BookDetail.tsx`          | Placeholder (A1/U6) |
| `frontend/src/index.css`                      | `@import "tailwindcss";` (v4) |
| `Makefile`                                    | `openapi`, `web` targets (A9/N10) |
| `.gitignore`                                  | frontend ignores + `.env.example` un-ignore (A9) |

---

## 0. Scaffold (A1)

From the repo root:

```bash
mkdir frontend && cd frontend
yarn create vite . --template react-ts
yarn add react-router-dom @tanstack/react-query zod
yarn add -D tailwindcss @tailwindcss/vite openapi-zod-client
```

Tailwind v4 (current — `4.3`) ships a first-party Vite plugin: no `init -p`, no
`postcss`/`autoprefixer`, no `tailwind.config.js`. Wire the plugin in
`vite.config.ts` (§1 below already includes it) and import Tailwind from CSS.
Content sources are auto-detected; theme customization lives in CSS via
`@theme`, not a JS config.

Replace `src/index.css` with the single Tailwind import, delete the Vite demo
boilerplate (`App.tsx`, `App.css`, assets) — `main.tsx` / `router.tsx` below
replace it.

```css
/* src/index.css */
@import "tailwindcss";
```

`index.html` keeps the Vite default (`<div id="root">` + `<script
type="module" src="/src/main.tsx">`), title `golden-book-rag`.

---

## 1. Env + Vite proxy (A2 — N3, N4, S2)

`frontend/src/config.ts`:

```ts
// Single source of the API base. Relative `/api` works in both dev (Vite proxy,
// vite.config.ts) and prod (reverse proxy, same origin) — no absolute URL is
// ever baked into the bundle. (Shaping D8/F1.)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
```

`frontend/src/vite-env.d.ts` (Vite scaffolds the reference line; add the typing):

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

`frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev origin (D8/G1-A): the browser only ever talks to the Vite origin; Vite
// proxies /api/* to the backend, stripping the /api prefix (backend routes are
// /books, not /api/books). No CORS, backend untouched. Prod uses a reverse proxy
// for the same /api path (out of scope).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
```

`frontend/.env.example`:

```
VITE_API_BASE_URL=/api
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

`frontend/package.json` script:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
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
import { API_BASE_URL } from "../config";

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
// success, throw ApiError on non-2xx or shape mismatch. No axios (D6).
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

## 5. App shell + routes (A1 — N1, N2, U4–U6)

`frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { router } from "./router";
import "./index.css";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
```

`frontend/src/router.tsx`:

```tsx
import { createBrowserRouter } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Home } from "./routes/Home";
import { BookDetail } from "./routes/BookDetail";

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Home /> },
      { path: "/books/:id", element: <BookDetail /> },
    ],
  },
]);
```

`frontend/src/components/Layout.tsx`:

```tsx
import { Link, Outlet } from "react-router-dom";

export function Layout() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <header className="border-b bg-white">
        <nav className="mx-auto flex max-w-3xl items-center px-4 py-3">
          <Link to="/" className="font-semibold">
            golden-book-rag
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
```

`frontend/src/routes/BookDetail.tsx`:

```tsx
import { useParams } from "react-router-dom";

// Placeholder route (Step 10+). Registered now so the shell + routing are real.
export function BookDetail() {
  const { id } = useParams();
  return <p className="text-sm text-zinc-500">Book {id} — coming soon.</p>;
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

`frontend/src/routes/Home.tsx` (N8 + U1):

```tsx
import { useQuery } from "@tanstack/react-query";
import { listBooks } from "../api/books";
import { Loading } from "../components/Loading";
import { ErrorState } from "../components/ErrorState";

// A7 — the connectivity smoke. Proves env → client → generated-zod → render
// end-to-end against the live backend. (No Library grid — that's Step 9.)
export function Home() {
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

# Frontend dev server (Vite). Run alongside `make api` (uvicorn) in another shell.
web:
	cd frontend && yarn dev
```

`.PHONY` line gains `openapi web`.

`.gitignore` — append:

```
# frontend
frontend/node_modules/
frontend/dist/
frontend/openapi.json
!frontend/.env.example
```

(`frontend/openapi.json` is the throwaway codegen input — only the generated
`schemas.ts` is committed. The `!frontend/.env.example` negates the existing
`.env.*` rule so the example is tracked.)

---

## Implementation Order

1. **Scaffold** (§0) — `yarn create vite`, add deps, wire the `@tailwindcss/vite`
   plugin + `@import "tailwindcss";`, drop demo boilerplate. `yarn dev` shows the
   blank Vite page.
2. **Env + proxy** (§1) — `config.ts`, `vite-env.d.ts`, `vite.config.ts`,
   `.env.example`.
3. **Codegen** (§2 + §7 `make openapi`) — boot nothing; run `make openapi` to
   produce `src/api/generated/schemas.ts`. Verify `BookList`/`BookOut` exports
   exist; fix the §4 import name if the generator sanitized it.
4. **Client** (§3) — `client.ts` (`request` + `ApiError`).
5. **Endpoint** (§4) — `books.ts` `listBooks`.
6. **Shell + routes** (§5) — `main.tsx`, `router.tsx`, `Layout`, `BookDetail`.
7. **Primitives + smoke** (§6) — `Loading`/`ErrorState`/`Empty`, `Home`.
8. **Repo wiring** (§7) — `Makefile`, `.gitignore`.
9. **Smoke run** — `make db-up` (if needed) → `make api` in one shell, `make web`
   in another → open `/`:
   - backend up with ≥0 books → "Connected · N books"
   - stop `uvicorn`, reload → friendly error state
   - visit `/books/abc` → placeholder in the shell
10. **Build gate** — `cd frontend && yarn build` green (`tsc -b && vite build`);
    `grep -ri "axios\|zodios" frontend/src` returns nothing (D6).

---

## Done When

- `/` renders **"Connected · N books"** with the live `GET /books` count, via
  `request` → Vite proxy → generated-zod parse → TanStack Query
- Backend down / non-2xx → `<ErrorState>` shows `ApiError.message` (friendly), no
  white screen or unhandled rejection
- A zod parse mismatch surfaces as the same error state, not a silent `any`
- The Vite proxy is the only path to the backend — no CORS added; the backend is
  untouched (`git status` shows only `frontend/`, `Makefile`, `.gitignore`)
- `/books/:id` renders the placeholder inside the shared shell; nav renders
- `make openapi` regenerates `src/api/generated/schemas.ts` offline
  (`app.openapi()`), and the file is committed
- `yarn build` is green; no axios/Zodios dependency is pulled in
- No feature screens, no per-endpoint fns beyond `listBooks`, no `impeccable`
  pass (Step 9+ scope)

## Step 9 Hand-off

Carried forward (see [shaping.md](./shaping.md) "Out of Scope"):

- **Library grid** (Step 9) is the first feature screen — it reuses `listBooks`
  (N7), the shared `<Loading>`/`<ErrorState>`/`<Empty>` primitives, and the
  TanStack Query pattern this step established. It adds status badges + cards.
- **Per-endpoint client fns** — each later step adds its `request(...)` one-liner
  (`getBook`, `getChunks`, `search`, `ask`, `uploadBook`, `deleteBook`) against
  the same wrapper + generated schemas.
- **Codegen on backend change** — re-run `make openapi` whenever a backend schema
  changes; the committed `schemas.ts` diff is the contract-drift signal.
- **`impeccable` polish** rides each feature screen, not this structural step.
- **Prod origin** is decided (D8: static build + reverse proxy, single `/api`
  origin, SPA fallback) but built at the deploy step; backend CORS only if FE/BE
  ever split origins.
