---
shaping: true
---

# Step 8: Frontend Foundation — Next.js App Router skeleton + typed client + OpenAPI→zod codegen — Shaping

Steps 1–7 shipped the backend: upload → parse/chunk → embed → store → search →
grounded `/ask`. The contract is **frozen and shipped** (see
[frontend_mvp.md](../../frontend_mvp.md) "Backend Contract") and FastAPI already
serves it as **`/openapi.json`**. Step 8 opens the **frontend MVP** — a thin,
honest client over that backend.

Step 8 is the **Foundation** slice (per `frontend_mvp.md` "Shaping Steps"):
stand up a Next.js (App Router) + React + TS app that talks to FastAPI through a
**typed, zod-validated API client whose schemas are generated from the backend's
OpenAPI**, behind an **app shell** (root layout) with an **env-configured base
URL** — proven by a **connectivity smoke** that reads `GET /books`. No feature
screens yet (Library = Step 9, Ask = Step 10, …); this step builds the seams
every later step plugs into — **including the auth seam** (D1/D9).

Carried in from `frontend_mvp.md` (verbatim drivers):

- Step 8 = `Foundation   typed API client, zod schemas, layout shell, env config`.
- Tech stack: React + TS, **TanStack Query**, **Tailwind**, a **typed `fetch`
  wrapper (no axios)**, **zod** mirroring backend pydantic.
- Error model: backend returns `{detail: string}`; one typed client maps status
  codes → friendly messages (413 size, 422 validation, 404 missing, 409 not ready).
- `refused: true` is a first-class UI state, not an error (matters Step 10; the
  schema must model it now).
- Discipline carried from the backend MVP: **ship the core loop first, leave the
  seams for later.** Foundation builds seams, not features.

## Settled decisions (pre-shape forks)

Resolved with the user before shaping (so the shape is concrete):

| # | Decision | Choice |
|---|----------|--------|
| D1 | Framework | **Next.js (App Router) + React + TS**, file-based routing. **Auth is almost certainly coming** (user-confirmed) and that drives the choice: App Router gives first-class auth seams — httpOnly-cookie sessions, `middleware.ts` route protection at the edge, and **server components that read the session at request time** — none of which a static SPA offers without a later migration. (Considered a Vite SPA: lighter and SSR-less, but auth would land as token-in-`localStorage` + client-side route guards, and moving to cookie/SSR auth afterward means rebuilding the data-fetch + routing layer. We pay the Next prod-server surface now to avoid that rework — see D9.) Aligns with `frontend_mvp.md`'s stated future FE. |
| D2 | Repo layout | **Polyglot repo, FE as a sibling `frontend/`.** Backend stays at root, **unchanged** — no `backend/` restructure (would churn a done, tested system: imports, `alembic.ini`, `docker-compose`, `Makefile`, CI paths, for zero payoff). Two toolchains (`uv` at root, **`yarn`** in `frontend/`) sharing an HTTP contract, not a dep graph. No JS-monorepo tool (one JS app + a Python service ⇒ workspaces earn nothing). |
| D3 | FE/BE type contract | **Generate zod from OpenAPI.** Codegen zod schemas from `/openapi.json` (`openapi-zod-client`, **schemas-only export**) → backend is the single source of truth; drift surfaces as a regenerated diff. **Schemas generated; the fetch wrapper + error model + endpoint fns stay hand-written** (keeps D6 "no axios" + the custom error map — a full Zodios client would drag in axios + its own error model, rejected). |
| D4 | Demo surface | **Connectivity smoke only** — shell renders a "Connected · N books" indicator from `GET /books`. **No Library screen** (Step 9). Proves env → client → zod → render with minimal surface. |
| D5 | Server state | **TanStack Query** — even the smoke's one read goes through it, establishing the pattern for Steps 9+. In App Router it mounts behind a `"use client"` provider boundary (`app/providers.tsx`). |
| D6 | HTTP | **Typed `fetch` wrapper, no axios** — works unchanged from client components (and, later, server components / route handlers). |
| D7 | Styling | **Tailwind** (plays well with the later `impeccable` pass) |
| D8 | Origin (dev + prod) | Next.js `next.config.ts` `rewrites()` maps `/api/:path*` → the backend (strips the `/api` prefix; backend routes are `/books`, not `/api/books`). Unlike a Vite dev proxy, a Next rewrite runs on the **Next server in both dev and prod**. **Dev:** target `http://localhost:8000`; browser stays same-origin, no CORS, backend untouched. **Prod:** the same rewrite runs on the Next server (target env-overridable), serving one origin, optionally behind a deploy reverse proxy. Either way same-origin → no CORS, and the `/api` base URL is identical dev↔prod so FE code never changes. Backend `CORSMiddleware` is only the fallback if FE/BE are ever forced onto different origins (out of scope). |
| D9 | Rendering | **Next.js App Router.** MVP feature data flows through **TanStack Query in client components** (the smoke included), so Step 8–14 screens behave like an SPA. But the framework server is **deliberately retained** — `middleware.ts`, server components, and route handlers are the seams auth will use (request-time session read, edge route protection, server-side token handling). This is the conscious inverse of an SSR-less SPA: we accept the framework-server surface because the auth seams it provides are the reason we chose Next (D1). No SSR data-fetching work is done *this* step; the capability is reserved, not exercised. |
| D10 | Indexability | **App is deliberately non-indexed (anti-SEO), not merely "no SEO."** The user does not want the app crawled/indexed. Because App Router can server-render crawlable HTML (unlike a pure client SPA), this is set **explicitly from the start**: a root `metadata.robots = { index: false, follow: false }` (propagates to every route) + an `app/robots.ts` that `Disallow: /`. **Caveat:** these only deter well-behaved crawlers — they are *not* access control. The real privacy gate is **auth** (D1), which puts every page behind a login wall a crawler can't reach. noindex is the cheap first layer; auth is the actual one. |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A Next.js App Router + React + TS app that talks to the FastAPI backend through a typed, zod-validated client **whose schemas are generated from `/openapi.json`**, behind an app shell with an env-configured base URL — proven by a connectivity smoke reading `GET /books` | Core goal |
| **R1** | **Project skeleton** | Must-have |
| R1.1 | New top-level `frontend/` (own `package.json`, isolated from the Python project) — Next.js App Router + TS, Tailwind wired, root `app/layout.tsx` shell + `app/page.tsx` (smoke) + `app/books/[id]/page.tsx` (placeholder); TanStack Query provider boundary (`app/providers.tsx`) | Must-have |
| R1.2 | **Env base URL** — `NEXT_PUBLIC_API_BASE_URL` read in **one** module (default `/api`), with `frontend/.env.example`; the browser→backend origin gap solved via Next `rewrites()` in dev (D8) | Must-have |
| **R2** | **Typed API client** | Must-have |
| R2.1 | A single typed `fetch` wrapper: base URL from env, JSON in/out, one place to add endpoints. No axios | Must-have |
| R2.2 | **Error model** — non-2xx → a typed `ApiError {status, detail, message}` mapping `{detail}` + status (404/409/413/422) to a friendly message; thrown so TanStack Query surfaces it | Must-have |
| R2.3 | One endpoint function wired for the smoke — `listBooks() → GET /books`; the wrapper makes adding the rest (Steps 9+) a one-liner | Must-have |
| **R3** | **OpenAPI→zod codegen** | Must-have |
| R3.1 | A **codegen step** turns the backend `/openapi.json` into zod schemas (`openapi-zod-client`, schemas-only) under `frontend/src/api/generated/`; covers all shared shapes (`Status`, `BookOut`, `ChunkBase`, `Citation`, `SearchHit`, `AskResponse`). Generated, not hand-written; TS types via `z.infer` | Must-have |
| R3.2 | The client **parses responses through the generated zod** at the boundary; a mismatch → typed error (catches backend drift, not a silent `any`) | Must-have |
| R3.3 | Codegen is **reproducible + offline** — a script dumps `openapi.json` from the app (`app.openapi()`) then runs the generator (`make openapi` / yarn script), so CI regenerates without a running server | Must-have |
| **R4** | **App shell** | Must-have |
| R4.1 | Root layout shell — header/nav + `{children}` + consistent chrome + the `QueryClientProvider` (via `app/providers.tsx`); routes (`/`, `/books/[id]`, …) exist via the App Router file tree even if placeholder | Must-have |
| R4.2 | Shared **loading / error / empty** primitives defined once (the smoke uses them; every later screen reuses them) | Must-have |
| **R5** | **Connectivity smoke (the demo)** | Must-have |
| R5.1 | The home route shows a "Connected · N books" indicator driven by `listBooks()` through TanStack Query → typed client → generated zod parse, with visible **loading** and **error** (backend down / parse fail) states. No Library grid | Must-have |
| **R6** | **Scope boundaries** | Must-have |
| R6.1 | No feature screens — no Library grid, Ask, Upload, chunk browser, status-polling hook, or delete (Steps 9–14) | Must-have |
| R6.2 | **No auth, SSR data-fetching, or streaming built this step.** Step 8 ships client-component data fetching (TanStack Query) only. But the architecture (App Router + `middleware.ts` seam + server-component data path) is **chosen so auth bolts on without a framework migration** (D1/D9) — the seam is reserved, not exercised | Must-have |
| R6.4 | **App is non-indexed from the first commit (D10)** — root `metadata.robots` noindex/nofollow + `app/robots.ts` `Disallow: /`. Cheap crawler deterrent only; not access control (auth is the real gate) | Must-have |
| R6.3 | No `impeccable` polish pass this step — foundation is structural; polish rides each feature step | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **Backend contract is frozen** — `POST /books/upload`, `GET /books`, `GET /books/{id}`, `GET /books/{id}/chunks`, `POST /books/{id}/search`, `POST /books/{id}/ask` (`?retrieve=`), `DELETE /books/{id}`. `{detail}` on error; status enum `pending\|processing\|ready\|failed`. Shapes: `BookOut`, `ChunkBase`, `Citation`, `SearchHit`, `AskResponse` |
| C0.2 | **FastAPI serves `/openapi.json`** (`app = FastAPI(title="golden-book-rag")`, `api/main.py`) — the codegen source of truth for D3/R3 |
| C0.3 | **No frontend exists** — repo is Python-only (`api/`, `services/`, `db/`, `pyproject.toml`). The "v1 front end mvp" commit added only `docs/frontend_mvp.md`, no code. `frontend/` is greenfield |
| C0.4 | **No CORS middleware** — `api/main.py` mounts only the books router; the browser→backend origin gap is solved by the Next.js `rewrites()` (dev) + the Next server / deploy proxy (prod) per D8, not a backend change |
| C0.5 | `.gitignore` ignores `.env.*` — a tracked `frontend/.env.example` needs an un-ignore line; add `frontend/node_modules`, `frontend/.next` to ignore |
| C0.6 | **Backend has no auth / ownership today** — `books` rows are global (no `owner_id`); every endpoint is open. The FE auth seam (D1) anticipates a later backend change adding owner-scoping; Step 8 does not depend on it |

## A: Thin foundation — generate schemas, hand-wire only the smoke (just-in-time)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Scaffold** `frontend/` — `create-next-app` (App Router, TS, Tailwind, `src/`). App shell `app/layout.tsx` (chrome + nav + `{children}` + `<Providers>` + root `metadata.robots` noindex/nofollow, D10), routes `app/page.tsx` (smoke) and `app/books/[id]/page.tsx` (placeholder); `app/robots.ts` `Disallow: /` (D10) | |
| **A2** | **Env + origin** — `src/lib/config.ts` reads `process.env.NEXT_PUBLIC_API_BASE_URL` once (default `/api`); `next.config.ts` `rewrites()` maps `/api/:path*` → `http://localhost:8000/:path*` (strips `/api`); `frontend/.env.example` | |
| **A3** | **OpenAPI→zod codegen** — `make openapi` (or yarn `gen:api`): dump `openapi.json` via `python -c "import json,api.main; print(json.dumps(api.main.app.openapi()))"` → `openapi-zod-client openapi.json -o src/api/generated/schemas.ts` (schemas-only). Generated `BookOut`/`Citation`/`AskResponse`/… zod + `z.infer` types | |
| **A4** | **Typed client** `src/api/client.ts` — `request<T>(path, schema, init)`: prefix base URL, JSON headers, non-2xx → parse `{detail}` → throw `ApiError {status, detail, message}` (status→message map), 2xx → `schema.parse(json)` | |
| **A5** | **Endpoints** `src/api/books.ts` — only `listBooks()` (`GET /books`, generated books-list schema). Others added in their steps | |
| **A6** | **TanStack Query** — `QueryClientProvider` in a `"use client"` `app/providers.tsx`, mounted in `app/layout.tsx`; smoke uses `useQuery(['books'], listBooks)` | |
| **A7** | **Connectivity smoke** `app/page.tsx` (`"use client"`) — shared `<Loading/>` / `<ErrorState/>` / "Connected · N books" badge from the query | |
| **A8** | **Shared state primitives** `src/components/` — `<Loading/>`, `<ErrorState detail/>`, `<Empty/>` (R4.2) | |
| **A9** | **Repo wiring** — root `Makefile` `web` target (`next dev`) + `openapi` target, `.gitignore` for `frontend/node_modules` + `frontend/.next`, un-ignore `frontend/.env.example` | |

## B: Full scaffold — generate the whole client + stub every screen up front

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A1–A4, A6–A9 identical | |
| **B2** | Either codegen the **full Zodios client** (all endpoints) *or* hand-write the whole endpoint surface (`getBook`, `getChunks`, `search`, `ask`, `uploadBook`, `deleteBook`) now — ahead of the screens that use them | ⚠️ |
| **B3** | Placeholder routes for every screen (`app/library`, `app/books/[id]` ask+chunks tabs, `app/upload`) scaffolded now | |

B front-loads the full client so later steps "just call it." But each endpoint
built now is unused until its step (Steps 9–14), untestable without its screen,
and may drift as those steps refine query params / error UX (`/ask`'s
`?retrieve=`, upload's multipart + 413). The full-Zodios variant *also* reopens
the axios + foreign-error-model question D3/D6 closed. The thin client (A4)
already makes adding each endpoint a one-liner, so B's payoff is small (⚠️ B2).

## G1: Origin — component fork (shared by A & B)

| Req | Requirement | Status | G1-A (Next rewrites + Next server) | G1-B (backend CORS) |
|-----|-------------|--------|:----------------------------------:|:-------------------:|
| R1.2 | Browser reaches the backend (dev + prod) | Must-have | ✅ | ✅ |
| R6.x | No backend scope creep in a FE step | Must-have | ✅ | ❌ |

**G1-A — Next.js `rewrites()` (Next server, dev + prod):** the
`next.config.ts` `rewrites()` run on the Next server in **both** dev and prod
(defined once); prod serves the app via the same Next server applying the `/api`
rewrite (single origin), optionally behind a deploy reverse proxy. Browser is
always same-origin → **no CORS, no backend change**. **G1-B — backend CORS:** `CORSMiddleware` in
`api/main.py` — only needed if FE/BE are forced onto different origins (e.g. FE on
a separate host, API elsewhere). **Lean: G1-A** (per D8); CORS recorded as the
split-origin fallback. The deploy topology (Next server on a platform vs behind
nginx/Caddy) is a deploy-step detail, not Step 8.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Next.js App Router → typed zod client (schemas from OpenAPI) + shell + env base URL, proven by a `GET /books` smoke | Core goal | ✅ | ✅ |
| R1.1 | `frontend/` Next.js App Router + TS, Tailwind, layout shell + routes | Must-have | ✅ | ✅ |
| R1.2 | Env base URL in one module + `.env.example`; origin via Next rewrites | Must-have | ✅ | ✅ |
| R2.1 | Single typed `fetch` wrapper, no axios | Must-have | ✅ | ❌ |
| R2.2 | Typed `ApiError` mapping `{detail}` + status → message, thrown | Must-have | ✅ | ❌ |
| R2.3 | `listBooks()` wired; adding more is a one-liner | Must-have | ✅ | ✅ |
| R3.1 | zod schemas **generated** from `/openapi.json`, all shared shapes | Must-have | ✅ | ✅ |
| R3.2 | Responses parsed through generated zod; mismatch → typed error | Must-have | ✅ | ✅ |
| R3.3 | Reproducible offline codegen (`app.openapi()` dump + generator) | Must-have | ✅ | ✅ |
| R4.1 | Layout shell + providers + (placeholder) routes in the App Router tree | Must-have | ✅ | ✅ |
| R4.2 | Shared loading/error/empty primitives | Must-have | ✅ | ✅ |
| R5.1 | "Connected · N books" smoke via Query→client→zod, loading+error | Must-have | ✅ | ✅ |
| R6.1 | No feature screens | Must-have | ✅ | ❌ |
| R6.2 | No auth/SSR/streaming built; auth seam reserved (D1/D9) | Must-have | ✅ | ✅ |
| R6.3 | No `impeccable` pass | Must-have | ✅ | ✅ |
| R6.4 | Non-indexed from first commit — root noindex + `robots.ts` (D10) | Must-have | ✅ | ✅ |

**Notes:**
- B fails R6.1: B2 builds the full endpoint surface before any screen consumes it
  — speculative feature-building, the creep R6.1 fences off.
- B (full-Zodios variant) fails R2.1/R2.2: a generated Zodios client pulls in
  axios and its own error model, displacing the hand-written wrapper + `ApiError`
  map D3/D6 chose. (The hand-written-all-endpoints variant of B keeps R2.1/R2.2 ✅
  but still fails R6.1.)
- A satisfies every R: generated schemas (R3) + a hand-written thin wrapper (R2) +
  only the smoke's endpoint (R6.1).

## Selected Shape

**A: Thin foundation (generate schemas, hand-wire just-in-time).** Decisions
baked in:

1. **Skeleton** — `frontend/` `create-next-app` (App Router, TS, Tailwind, `src/`);
   `app/layout.tsx` shell + `<Providers>`, `app/page.tsx` (smoke) +
   `app/books/[id]/page.tsx` (placeholder).
2. **Codegen** — schemas-only `openapi-zod-client` off a dumped `openapi.json`
   (`make openapi`, reproducible offline). Generated zod = source of truth.
3. **Client** — one hand-written typed `fetch` wrapper (`request<T>(path, schema)`),
   `ApiError` status→message map, generated-zod parse on success. Only
   `listBooks()` wired now.
4. **Origin** — **G1-A**: dev Next `rewrites()` `/api/:path*` → `:8000`; prod the
   Next server applies the same rewrite (single origin), optionally behind a
   deploy proxy. No CORS. Backend CORS = split-origin fallback (out of scope).
5. **Demo** — connectivity smoke ("Connected · N books") + shared loading/error/
   empty primitives; no Library grid.
6. **Auth seam (reserved, not built)** — App Router + `middleware.ts` + the
   server-component data path are chosen so auth (httpOnly-cookie session, edge
   route protection) lands later without a framework migration (D1/D9, C0.6).

Open forks remaining (resolve in breadboard, not blocking):

- **F1 — env base URL value:** `NEXT_PUBLIC_API_BASE_URL=/api` (relative, leans on
  the dev `rewrites()` + the same-origin prod server) vs an absolute URL. Lean:
  `/api` relative — one value, identical dev↔prod, no prod URL baked into the
  client bundle.
- **F2 — codegen invocation home:** root `Makefile` target vs `frontend/package.json`
  script vs both. Lean: a `frontend` yarn `gen:api` script that the root `Makefile`
  calls — single definition, callable from either side.
- **F3 — generated dir tracked vs gitignored + built in CI:** commit
  `src/api/generated/` (diff-reviewable drift) vs regenerate in CI. Lean: **commit
  it** — the drift-as-diff benefit (D3) only lands if the generated file is in the
  tree to diff.

A has no ⚠️ unknowns: Next.js `rewrites()` and `openapi-zod-client` are standard;
the contract is frozen and already emitted as `/openapi.json`.

## Out of Scope — deferred (Step 9+ hand-off)

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Auth / login (cookie session, `middleware.ts` route protection, server-component session read)** | Step 8 builds the App Router *seam* for it (D1/D9) but ships no auth; needs the backend owner-scoping change too (C0.6) | Dedicated auth step (post-MVP) |
| **Library grid + status badges** | Foundation proves wiring with a smoke, not a feature screen | Step 9 |
| **Ask panel** (answer + citations + refusal + RAG-vs-no-RAG compare) | Product's heart; own shape + `impeccable` pass | Step 10 |
| **Sources / chunk browser / raw search** | — | Step 11 |
| **Upload form** (multipart, 413 guard, optimistic pending) | — | Step 12 |
| **Status polling hook** (`useBookStatus`) | Foundation registers the seam (TanStack Query); polling is a feature concern | Step 13 |
| **Delete + confirm** | — | Step 14 |
| **`impeccable` polish pass** | Structural step; polish rides each feature screen | Each feature step |
| **SSR / server-component data fetching** | Capability reserved by D9; MVP screens are client components. First real use is the auth session read | Auth step / as needed |
| **SEO / indexability** | Not deferred — **inverted**: the app is deliberately non-indexed from the first commit (D10/R6.4). No SEO work will be added; if anything, auth tightens it further | N/A (anti-goal) |
| **Prod deploy topology** (Next server on a platform vs behind nginx/Caddy) | Step 8's demo is `yarn dev` + `uvicorn` via the Next dev rewrite; the prod single-origin model is **decided** (D8) but its topology is a deploy detail | Deploy step |
| **Backend CORS middleware** (G1-B) | The single-origin model needs no CORS; CORS is only the split-origin fallback | If FE/BE ever land on different origins |
| **Per-endpoint client fns** | Thin shape adds endpoints per step | Steps 9+ |
| **Backend answer-quality eval / cross-book ask / reranking / owner-scoping** | Backend follow-ups, parked while the FE MVP ships | `thoughts.md` §6 (parking lot) |

## Next Step

Breadboard Shape A (the `frontend/` scaffold + env/Next-rewrites + OpenAPI→zod
codegen + hand-written `client`/`ApiError` + `listBooks` + TanStack Query
provider boundary + `app/layout.tsx`/routes + shared primitives + the smoke
route), then slice. A single vertical slice is expected — one app skeleton whose
demo is the connectivity smoke; per-endpoint client fns and feature routes are
Steps 9+.
