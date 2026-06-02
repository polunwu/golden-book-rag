---
shaping: true
---

# Step 8: Frontend Foundation — Vite SPA skeleton + typed client + OpenAPI→zod codegen — Shaping

Steps 1–7 shipped the backend: upload → parse/chunk → embed → store → search →
grounded `/ask`. The contract is **frozen and shipped** (see
[frontend_mvp.md](../../frontend_mvp.md) "Backend Contract") and FastAPI already
serves it as **`/openapi.json`**. Step 8 opens the **frontend MVP** — a thin,
honest client over that backend.

Step 8 is the **Foundation** slice (per `frontend_mvp.md` "Shaping Steps"):
stand up a Vite + React + TS SPA that talks to FastAPI through a **typed,
zod-validated API client whose schemas are generated from the backend's
OpenAPI**, behind an **app shell** with an **env-configured base URL** — proven
by a **connectivity smoke** that reads `GET /books`. No feature screens yet
(Library = Step 9, Ask = Step 10, …); this step builds the seams every later
step plugs into.

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
| D1 | Framework | **Vite + React + TS SPA**, routing via **`react-router`**. MVP has no SSR/SEO need (D9), so Vite's static-only output is the right fit and the simplest origin/security story (see D8). (Considered Next.js for familiarity, but its prod-server attack surface + the `output:'export'` vs rewrites friction don't pay off for an SSR-less MVP.) |
| D2 | Repo layout | **Polyglot repo, FE as a sibling `frontend/`.** Backend stays at root, **unchanged** — no `backend/` restructure (would churn a done, tested system: imports, `alembic.ini`, `docker-compose`, `Makefile`, CI paths, for zero payoff). Two toolchains (`uv` at root, **`yarn`** in `frontend/`) sharing an HTTP contract, not a dep graph. No JS-monorepo tool (one JS app + a Python service ⇒ workspaces earn nothing). |
| D3 | FE/BE type contract | **Generate zod from OpenAPI.** Codegen zod schemas from `/openapi.json` (`openapi-zod-client`, **schemas-only export**) → backend is the single source of truth; drift surfaces as a regenerated diff. **Schemas generated; the fetch wrapper + error model + endpoint fns stay hand-written** (keeps D6 "no axios" + the custom error map — a full Zodios client would drag in axios + its own error model, rejected). |
| D4 | Demo surface | **Connectivity smoke only** — shell renders a "Connected · N books" indicator from `GET /books`. **No Library screen** (Step 9). Proves env → client → zod → render with minimal surface. |
| D5 | Server state | **TanStack Query** — even the smoke's one read goes through it, establishing the pattern for Steps 9+ |
| D6 | HTTP | **Typed `fetch` wrapper, no axios** |
| D7 | Styling | **Tailwind** (plays well with the later `impeccable` pass) |
| D8 | Origin (dev + prod) | **Dev:** Vite `server.proxy` maps `/api/*` → `http://localhost:8000` (strips the `/api` prefix); browser stays same-origin, no CORS, backend untouched, dev-server-only. **Prod:** `vite build` is pure static → served behind a **reverse proxy (Caddy)** as a single origin (`/` → static, `/api/*` → backend, SPA fallback to `index.html`); still no CORS, no framework server. The `/api` prefix + base URL is identical dev↔prod, so FE code never changes. Backend `CORSMiddleware` is only the fallback if FE/BE are ever forced onto different origins (out of scope). |
| D9 | Rendering | **Client-only SPA — no SSR/SEO** (user: "useless for me"). Vite outputs a static bundle by default; there is **no framework server in prod**, which also collapses the entire class of server-side framework CVEs (middleware-bypass / SSR-SSRF / RSC-RCE / cache-poisoning) to non-applicable. Data via TanStack Query on the client; routing client-side via `react-router` |

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A Vite React+TS SPA skeleton that talks to the FastAPI backend through a typed, zod-validated client **whose schemas are generated from `/openapi.json`**, behind an app shell with an env-configured base URL — proven by a connectivity smoke reading `GET /books` | Core goal |
| **R1** | **Project skeleton** | Must-have |
| R1.1 | New top-level `frontend/` (own `package.json`, isolated from the Python project) — Vite + React + TS, Tailwind wired, `react-router` with the route shell (`<Layout>` + `<Outlet/>`) registered (feature routes are placeholders) | Must-have |
| R1.2 | **Env base URL** — `VITE_API_BASE_URL` read in **one** module (default `/api`), with `frontend/.env.example`; the browser→backend origin gap solved via Vite `server.proxy` in dev (D8) | Must-have |
| **R2** | **Typed API client** | Must-have |
| R2.1 | A single typed `fetch` wrapper: base URL from env, JSON in/out, one place to add endpoints. No axios | Must-have |
| R2.2 | **Error model** — non-2xx → a typed `ApiError {status, detail, message}` mapping `{detail}` + status (404/409/413/422) to a friendly message; thrown so TanStack Query surfaces it | Must-have |
| R2.3 | One endpoint function wired for the smoke — `listBooks() → GET /books`; the wrapper makes adding the rest (Steps 9+) a one-liner | Must-have |
| **R3** | **OpenAPI→zod codegen** | Must-have |
| R3.1 | A **codegen step** turns the backend `/openapi.json` into zod schemas (`openapi-zod-client`, schemas-only) under `frontend/src/api/generated/`; covers all shared shapes (`Status`, `BookOut`, `ChunkBase`, `Citation`, `SearchHit`, `AskResponse`). Generated, not hand-written; TS types via `z.infer` | Must-have |
| R3.2 | The client **parses responses through the generated zod** at the boundary; a mismatch → typed error (catches backend drift, not a silent `any`) | Must-have |
| R3.3 | Codegen is **reproducible + offline** — a script dumps `openapi.json` from the app (`app.openapi()`) then runs the generator (`make openapi` / yarn script), so CI regenerates without a running server | Must-have |
| **R4** | **App shell** | Must-have |
| R4.1 | Layout shell — header/nav + `<Outlet/>` + consistent chrome + the `QueryClientProvider`; routes (`/`, `/books/:id`, …) registered even if placeholder | Must-have |
| R4.2 | Shared **loading / error / empty** primitives defined once (the smoke uses them; every later screen reuses them) | Must-have |
| **R5** | **Connectivity smoke (the demo)** | Must-have |
| R5.1 | The home route shows a "Connected · N books" indicator driven by `listBooks()` through TanStack Query → typed client → generated zod parse, with visible **loading** and **error** (backend down / parse fail) states. No Library grid | Must-have |
| **R6** | **Scope boundaries** | Must-have |
| R6.1 | No feature screens — no Library grid, Ask, Upload, chunk browser, status-polling hook, or delete (Steps 9–14) | Must-have |
| R6.2 | **Client-only SPA (D9):** no auth, no SSR, no SEO/meta, no streaming; all data via TanStack Query on the client | Must-have |
| R6.3 | No `impeccable` polish pass this step — foundation is structural; polish rides each feature step | Must-have |

## CURRENT: existing system (baseline)

| Part | Mechanism |
|------|-----------|
| C0.1 | **Backend contract is frozen** — `POST /books/upload`, `GET /books`, `GET /books/{id}`, `GET /books/{id}/chunks`, `POST /books/{id}/search`, `POST /books/{id}/ask` (`?retrieve=`), `DELETE /books/{id}`. `{detail}` on error; status enum `pending\|processing\|ready\|failed`. Shapes: `BookOut`, `ChunkBase`, `Citation`, `SearchHit`, `AskResponse` |
| C0.2 | **FastAPI serves `/openapi.json`** (`app = FastAPI(title="golden-book-rag")`, `api/main.py`) — the codegen source of truth for D3/R3 |
| C0.3 | **No frontend exists** — repo is Python-only (`api/`, `services/`, `db/`, `pyproject.toml`). The "v1 front end mvp" commit added only `docs/frontend_mvp.md`, no code. `frontend/` is greenfield |
| C0.4 | **No CORS middleware** — `api/main.py` mounts only the books router; the browser→backend origin gap is solved by the Vite dev proxy (dev) + a reverse proxy (prod) per D8, not a backend change |
| C0.5 | `.gitignore` ignores `.env.*` — a tracked `frontend/.env.example` needs an un-ignore line; add `frontend/node_modules`, `frontend/dist` to ignore |

## A: Thin foundation — generate schemas, hand-wire only the smoke (just-in-time)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Scaffold** `frontend/` — Vite `react-ts` + Tailwind + `react-router`. App shell `<Layout>` (chrome + nav + `<Outlet/>`), routes `/` (smoke) and `/books/:id` (placeholder) | |
| **A2** | **Env + origin** — `src/config.ts` reads `import.meta.env.VITE_API_BASE_URL` once (default `/api`); `vite.config.ts` `server.proxy` maps `/api` → `http://localhost:8000` with `rewrite: p => p.replace(/^\/api/, '')`; `frontend/.env.example` | |
| **A3** | **OpenAPI→zod codegen** — `make openapi` (or yarn `gen:api`): dump `openapi.json` via `python -c "import json,api.main; print(json.dumps(api.main.app.openapi()))"` → `openapi-zod-client openapi.json -o src/api/generated/schemas.ts` (schemas-only). Generated `BookOut`/`Citation`/`AskResponse`/… zod + `z.infer` types | |
| **A4** | **Typed client** `src/api/client.ts` — `request<T>(path, schema, init)`: prefix base URL, JSON headers, non-2xx → parse `{detail}` → throw `ApiError {status, detail, message}` (status→message map), 2xx → `schema.parse(json)` | |
| **A5** | **Endpoints** `src/api/books.ts` — only `listBooks()` (`GET /books`, generated books-list schema). Others added in their steps | |
| **A6** | **TanStack Query** — `QueryClientProvider` mounted at the root (`src/main.tsx`); smoke uses `useQuery(['books'], listBooks)` | |
| **A7** | **Connectivity smoke** `src/routes/Home.tsx` — shared `<Loading/>` / `<ErrorState/>` / "Connected · N books" badge from the query | |
| **A8** | **Shared state primitives** `src/components/` — `<Loading/>`, `<ErrorState detail/>`, `<Empty/>` (R4.2) | |
| **A9** | **Repo wiring** — root `Makefile` `dev` target (uvicorn + `vite`), `.gitignore` for `frontend/node_modules` + `frontend/dist`, un-ignore `frontend/.env.example` | |

## B: Full scaffold — generate the whole client + stub every screen up front

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | A1–A4, A6–A9 identical | |
| **B2** | Either codegen the **full Zodios client** (all endpoints) *or* hand-write the whole endpoint surface (`getBook`, `getChunks`, `search`, `ask`, `uploadBook`, `deleteBook`) now — ahead of the screens that use them | ⚠️ |
| **B3** | Placeholder routes for every screen (`/`, `/library`, `/books/:id` ask+chunks tabs, `/upload`) scaffolded now | |

B front-loads the full client so later steps "just call it." But each endpoint
built now is unused until its step (Steps 9–14), untestable without its screen,
and may drift as those steps refine query params / error UX (`/ask`'s
`?retrieve=`, upload's multipart + 413). The full-Zodios variant *also* reopens
the axios + foreign-error-model question D3/D6 closed. The thin client (A4)
already makes adding each endpoint a one-liner, so B's payoff is small (⚠️ B2).

## G1: Origin — component fork (shared by A & B)

| Req | Requirement | Status | G1-A (Vite proxy + reverse proxy) | G1-B (backend CORS) |
|-----|-------------|--------|:---------------------------------:|:-------------------:|
| R1.2 | Browser reaches the backend (dev + prod) | Must-have | ✅ | ✅ |
| R6.x | No backend scope creep in a FE step | Must-have | ✅ | ❌ |

**G1-A — Vite proxy (dev) + reverse proxy (prod):** dev uses `server.proxy`
(dev-server-only); prod serves the static `dist/` behind a reverse proxy (Caddy)
as a single origin. Browser is always same-origin → **no CORS, no backend change,
no framework server**. **G1-B — backend CORS:** `CORSMiddleware` in `api/main.py`
— only needed if FE/BE are forced onto different origins (e.g. FE on a static
host, API elsewhere). **Lean: G1-A** (per D8); CORS recorded as the split-origin
fallback. The reverse-proxy *tooling* choice (Caddy vs nginx vs platform proxy)
is a deploy-step detail, not Step 8.

## Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | Vite SPA → typed zod client (schemas from OpenAPI) + shell + env base URL, proven by a `GET /books` smoke | Core goal | ✅ | ✅ |
| R1.1 | `frontend/` Vite+React+TS, Tailwind, `react-router` shell | Must-have | ✅ | ✅ |
| R1.2 | Env base URL in one module + `.env.example`; origin via Vite proxy | Must-have | ✅ | ✅ |
| R2.1 | Single typed `fetch` wrapper, no axios | Must-have | ✅ | ❌ |
| R2.2 | Typed `ApiError` mapping `{detail}` + status → message, thrown | Must-have | ✅ | ❌ |
| R2.3 | `listBooks()` wired; adding more is a one-liner | Must-have | ✅ | ✅ |
| R3.1 | zod schemas **generated** from `/openapi.json`, all shared shapes | Must-have | ✅ | ✅ |
| R3.2 | Responses parsed through generated zod; mismatch → typed error | Must-have | ✅ | ✅ |
| R3.3 | Reproducible offline codegen (`app.openapi()` dump + generator) | Must-have | ✅ | ✅ |
| R4.1 | Layout shell + providers + registered (placeholder) routes | Must-have | ✅ | ✅ |
| R4.2 | Shared loading/error/empty primitives | Must-have | ✅ | ✅ |
| R5.1 | "Connected · N books" smoke via Query→client→zod, loading+error | Must-have | ✅ | ✅ |
| R6.1 | No feature screens | Must-have | ✅ | ❌ |
| R6.2 | Client-only SPA: no auth/SSR/SEO/streaming (D9) | Must-have | ✅ | ✅ |
| R6.3 | No `impeccable` pass | Must-have | ✅ | ✅ |

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

1. **Skeleton** — `frontend/` Vite `react-ts` + Tailwind + `react-router`;
   `<Layout>` shell with `/` (smoke) + `/books/:id` (placeholder).
2. **Codegen** — schemas-only `openapi-zod-client` off a dumped `openapi.json`
   (`make openapi`, reproducible offline). Generated zod = source of truth.
3. **Client** — one hand-written typed `fetch` wrapper (`request<T>(path, schema)`),
   `ApiError` status→message map, generated-zod parse on success. Only
   `listBooks()` wired now.
4. **Origin** — **G1-A**: dev Vite `server.proxy` `/api/*` → `:8000`; prod static
   `dist/` behind a reverse proxy (single origin, SPA fallback). No CORS, no
   framework server. Backend CORS = split-origin fallback (out of scope).
5. **Demo** — connectivity smoke ("Connected · N books") + shared loading/error/
   empty primitives; no Library grid.

Open forks remaining (resolve in breadboard, not blocking):

- **F1 — env base URL value:** `VITE_API_BASE_URL=/api` (relative, leans on the
  dev proxy + the same-origin prod reverse proxy) vs an absolute URL. Lean: `/api`
  relative — one value, identical dev↔prod, no prod URL baked into the bundle.
- **F2 — codegen invocation home:** root `Makefile` target vs `frontend/package.json`
  script vs both. Lean: a `frontend` yarn `gen:api` script that the root `Makefile`
  calls — single definition, callable from either side.
- **F3 — generated dir tracked vs gitignored + built in CI:** commit
  `src/api/generated/` (diff-reviewable drift) vs regenerate in CI. Lean: **commit
  it** — the drift-as-diff benefit (D3) only lands if the generated file is in the
  tree to diff.

A has no ⚠️ unknowns: Vite `server.proxy` and `openapi-zod-client` are standard;
the contract is frozen and already emitted as `/openapi.json`.

## Out of Scope — deferred (Step 9+ hand-off)

| Topic | Why deferred | Where it resurfaces |
|-------|--------------|---------------------|
| **Library grid + status badges** | Foundation proves wiring with a smoke, not a feature screen | Step 9 |
| **Ask panel** (answer + citations + refusal + RAG-vs-no-RAG compare) | Product's heart; own shape + `impeccable` pass | Step 10 |
| **Sources / chunk browser / raw search** | — | Step 11 |
| **Upload form** (multipart, 413 guard, optimistic pending) | — | Step 12 |
| **Status polling hook** (`useBookStatus`) | Foundation registers the seam (TanStack Query); polling is a feature concern | Step 13 |
| **Delete + confirm** | — | Step 14 |
| **`impeccable` polish pass** | Structural step; polish rides each feature screen | Each feature step |
| **Prod reverse-proxy tooling** (Caddy vs nginx vs platform) | Step 8's demo is `yarn dev` + `uvicorn` via the Vite proxy; the prod single-origin reverse proxy is **decided** (D8) but its tooling is a deploy detail | Deploy step |
| **Backend CORS middleware** (G1-B) | The reverse-proxy single-origin model needs no CORS; CORS is only the split-origin fallback | If FE/BE ever land on different origins |
| **Per-endpoint client fns** | Thin shape adds endpoints per step | Steps 9+ |
| **Backend answer-quality eval / cross-book ask / reranking** | Backend follow-ups, parked while the FE MVP ships | `thoughts.md` §6 (parking lot) |

## Next Step

Breadboard Shape A (the `frontend/` scaffold + env/Vite-proxy + OpenAPI→zod
codegen + hand-written `client`/`ApiError` + `listBooks` + TanStack Query
provider + `<Layout>`/routes + shared primitives + the smoke route), then slice.
A single vertical slice is expected — one app skeleton whose demo is the
connectivity smoke; per-endpoint client fns and feature routes are Steps 9+.
