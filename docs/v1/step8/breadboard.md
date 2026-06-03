---
shaping: true
---

# Step 8 Breadboard — Frontend Foundation (Shape A)

Details the **selected Shape A** from [shaping.md](./shaping.md) into concrete
affordances + wiring. Designed from the shaped parts A1–A9; the backend
(`/books`, `/openapi.json`) is the existing system the new pieces connect to.

Mechanism IDs (A1–A9) reference Shape A in `shaping.md`.

## Places

| # | Place | Description |
|---|-------|-------------|
| P1 | Home + App shell (frontend) | `/` — `app/layout.tsx` root chrome (nav + `{children}` + `<Providers>`) wrapping the **connectivity-smoke** page (`app/page.tsx`). The demo place |
| P2 | Book detail placeholder (frontend) | `/books/[id]` — registered placeholder route (`app/books/[id]/page.tsx`), real screen is Steps 10+ |
| P3 | Backend (FastAPI) | Existing. `GET /books` (smoke data) + `GET /openapi.json` (codegen source) |
| T1 | Codegen (build-time trigger) | Not a runtime place — `make openapi` / yarn `gen:api` regenerates the zod schemas from `/openapi.json` |

`app/layout.tsx` is shared chrome around both P1 and P2 (App Router nests every
route under the root layout); nav lives in P1's table.

## UI Affordances

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| U1 | P1 | Home (`app/page.tsx`) | "Connected · N books" badge | render | — | — |
| U2 | P1 | `<Loading/>` (shared) | loading skeleton/spinner | render | — | — |
| U3 | P1 | `<ErrorState detail/>` (shared) | friendly error message | render | — | — |
| U4 | P1 | `app/layout.tsx` | header/nav (app title + Home link, `next/link`) | click | → P1 | — |
| U5 | P1 | `app/layout.tsx` | `{children}` (renders active route) | render | — | — |
| U6 | P2 | `app/books/[id]/page.tsx` | placeholder "Book {id} — coming soon" | render | — | — |
| U7 | P1 | `<Empty/>` (shared) | empty primitive — defined (R4.2), unused by the smoke | render | — | — |

## Code Affordances

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| N1 | P1 | `app/layout.tsx` (A1, A6) | root layout: render chrome, wrap `{children}` in `<Providers>` | render | → N2 | — |
| N2 | P1 | `app/providers.tsx` (A6) | `"use client"` — mount `QueryClientProvider` | call | → P1, → P2 | — |
| N3 | P1 | `src/lib/config.ts` (A2) | `API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL` (default `/api`) | config | — | → N5 |
| N4 | P1 | `next.config.ts` (A2) | `rewrites()` `/api/:path*` → `http://localhost:8000/:path*` (strips `/api`) | call | → P3 | — |
| N5 | P1 | `src/api/client.ts` (A4) | `request<T>(path, schema, init)` — prefix base URL, JSON, 2xx→`schema.parse`, non-2xx→throw | call | → N4, → N6 | → N7 |
| N6 | P1 | `src/api/client.ts` (A4) | `ApiError {status, detail, message}` — `{detail}` + status→message map | call | — | → N8 |
| N7 | P1 | `src/api/books.ts` (A5) | `listBooks()` → `request('/books', BookList)` | call | → N5 | → N8 |
| N8 | P1 | Home (A6) | `useQuery(['books'], listBooks)` | observe | → N7 | → U1, → U2, → U3 |
| N10 | T1 | `Makefile` / `gen:api` (A3) | dump `openapi.json` via `app.openapi()` | call | → N21, → N11 | — |
| N11 | T1 | `openapi-zod-client` (A3) | generate schemas-only zod | call | → S1 | — |
| N20 | P3 | `api/routers/books.py` | `GET /books` → `{items: BookOut[]}` | call | — | → N5 |
| N21 | P3 | `api/main.py` | `GET /openapi.json` (`app.openapi()`) | call | — | → N10 |

## Data Stores

| # | Place | Store | Description | Written by | Read by |
|---|-------|-------|-------------|------------|---------|
| S1 | P1 | `src/api/generated/schemas.ts` (A3) | generated zod schemas (`Status`, `BookOut`, `ChunkBase`, `Citation`, `SearchHit`, `AskResponse`, `BookList`) + `z.infer` types | N11 (codegen) | N5 (parse), N7 (schema arg) |
| S2 | P1 | `frontend/.env` `NEXT_PUBLIC_API_BASE_URL` (A2) | env base URL (external store, default `/api`) | dev/ops | N3 |

## Wiring notes

- **Smoke (runtime):** the root layout (`N1`) wraps the tree in `<Providers>`
  (`N2`); `app/page.tsx` mounts → `N8` runs `listBooks` (`N7`) → `request` (`N5`)
  prefixes `API_BASE_URL` (`N3`←`S2`), fetches through the Next rewrite (`N4`) →
  backend `GET /books` (`N20`) → JSON returns to `N5` → `N5` parses with the
  generated `BookList` (`S1`). Success → `BookOut[]` flows `N7`→`N8`→**U1**
  ("Connected · N books"). `N8.isLoading`→**U2**; non-2xx **or** zod parse
  mismatch → `N5` throws `ApiError` (`N6`) → `N8.error`→**U3**.
- **Codegen (build-time):** `N10` reads backend `/openapi.json` (`N21`) → runs
  `openapi-zod-client` (`N11`) → writes `S1`. Decoupled from the runtime path; S1
  is committed (F3) so drift shows as a diff.
- **Origin:** `N4` (Next `rewrites()`) is the only dev bridge to P3 — no CORS,
  backend untouched (D8). In prod the same `/api` path is rewritten by the Next
  server (out of scope).
- **Auth seam (reserved, D1/D9):** the App Router shell (`N1`) and the
  same-origin Next server (`N4`) are the future home of `middleware.ts` route
  protection and a server-side session read. Not wired this step; the `request`
  wrapper (`N5`) is the single place a session header/cookie pass-through lands
  later.
- **Non-indexed (D10):** the root layout (`N1`) sets `metadata.robots`
  noindex/nofollow and `app/robots.ts` emits `Disallow: /`. These are static
  policy with no runtime wiring (like `globals.css`/`Makefile`/`.gitignore`), so
  they carry no affordance ID — noted here for traceability. Crawler deterrent
  only, not access control (auth is the real gate).

## Diagram

```mermaid
flowchart TB
    subgraph P1["P1: Home + App shell (frontend)"]
        U1["U1: 'Connected · N books' badge"]
        U2["U2: <Loading/>"]
        U3["U3: <ErrorState/>"]
        U4["U4: nav (Home link)"]
        U5["U5: {children}"]
        U7["U7: <Empty/> (defined, unused)"]
        N1["N1: app/layout.tsx (root shell)"]
        N2["N2: app/providers.tsx (QueryClientProvider)"]
        N3["N3: lib/config API_BASE_URL"]
        N4["N4: next.config rewrites /api"]
        N5["N5: request(path, schema)"]
        N6["N6: ApiError (status→msg)"]
        N7["N7: listBooks()"]
        N8["N8: useQuery(['books'])"]
        S1["S1: generated/schemas.ts (zod)"]
        S2["S2: .env NEXT_PUBLIC_API_BASE_URL"]
    end

    subgraph P2["P2: Book detail placeholder"]
        U6["U6: 'Book {id} — coming soon'"]
    end

    subgraph T1["T1: Codegen (build-time)"]
        N10["N10: dump openapi.json"]
        N11["N11: openapi-zod-client"]
    end

    subgraph P3["P3: Backend (FastAPI)"]
        N20["N20: GET /books"]
        N21["N21: GET /openapi.json"]
    end

    N1 --> N2
    N2 --> P1
    N2 --> P2
    U4 --> P1

    N8 --> N7
    N7 --> N5
    N5 --> N4
    N5 --> N6
    N4 --> P3
    N20 -.-> N5
    S2 -.-> N3
    N3 -.-> N5
    S1 -.-> N5
    S1 -.-> N7
    N6 -.-> N8
    N5 -.-> N7
    N7 -.-> N8
    N8 -.-> U1
    N8 -.-> U2
    N8 -.-> U3

    N10 --> N21
    N21 -.-> N10
    N10 --> N11
    N11 --> S1

    classDef ui fill:#ffb6c1,stroke:#d87093,color:#000
    classDef nonui fill:#d3d3d3,stroke:#808080,color:#000
    classDef store fill:#e6e6fa,stroke:#9370db,color:#000
    class U1,U2,U3,U4,U5,U6,U7 ui
    class N1,N2,N3,N4,N5,N6,N7,N8,N10,N11,N20,N21 nonui
    class S1,S2 store
```

## Slicing

Step 8 is **one vertical slice** (per `shaping.md` Next Step): the whole skeleton
ships together, demoed by the connectivity smoke — there's no smaller demo-able
increment (a client with no shell, or a shell with no client, demos nothing).

| # | Slice | Mechanism | Affordances | Demo |
|---|-------|-----------|-------------|------|
| V1 | Connectivity smoke | A1–A9 | all (U1–U7, N1–N11, N20–N21, S1–S2) | `yarn dev` + `uvicorn` → `/` shows "Connected · N books"; stop backend → error state; all via typed client + generated zod |

## Next Step

Write [slices.md](./slices.md) formalizing the single V1 slice (affordance table
+ demo + "done when"), then [V1-plan.md](./V1-plan.md) with concrete file diffs
(`frontend/` scaffold, `next.config.ts` rewrites, `lib/config.ts`, `api/client.ts`
+ `ApiError`, `api/books.ts`, the `gen:api` codegen wiring, `app/layout.tsx` +
`app/providers.tsx` + routes, shared primitives, `app/page.tsx` smoke, `Makefile`
`web`/`openapi`, `.gitignore`).
