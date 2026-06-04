---
shaping: true
---

# Step 9: Library — Breadboard (Shape A)

Detailing Shape A (`docs/v1/step9/shaping.md`) into concrete affordances. The
data path (TanStack Query → `listBooks()` → `request<T>` → `BookList` zod) and
the loading/error/empty primitives **already exist** from Step 8 — they appear
here as existing affordances the new presentational pieces wire into. New
affordances: `<BookCard/>`, `<StatusBadge/>`, the `formatDate`/title-fallback
helper, and the list container that replaces the smoke render in `app/page.tsx`.

## Places

| # | Place | Description |
|---|-------|-------------|
| P1 | Library (`/`) — frontend | `app/page.tsx`, the Library screen (was the Step 8 smoke) |
| P2 | Book page (`/books/[id]`) — frontend | Existing placeholder route; the card's navigation target |
| P3 | Backend | FastAPI `GET /books` |

## UI Affordances

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| U1 | P1 | `app/page.tsx` | `<Loading/>` (connecting) | render | — | — |
| U2 | P1 | `app/page.tsx` | `<ErrorState detail/>` | render | — | — |
| U3 | P1 | `app/page.tsx` | `<Empty label="No books yet."/>` | render | — | — |
| U4 | P1 | `BookList` container | book list/grid (newest-first) | render | → U5 | — |
| U5 | P1 | `BookCard` | whole card (`next/link`) | click | → P2 | — |
| U6 | P1 | `BookCard` | title (null-safe) | render | — | — |
| U7 | P1 | `StatusBadge` | status badge (4 states) | render | — | — |
| U8 | P1 | `BookCard` | created date | render | — | — |

## Code Affordances

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| N1 | P1 | `app/page.tsx` | `useQuery(['books'], listBooks)` | observe | → N2 | → U1, U2, U3, U4 |
| N2 | P1 | `api/books.ts` | `listBooks()` *(exists)* | call | → N3 | → N1 |
| N3 | P1 | `api/client.ts` | `request('/books', BookList)` *(exists)* | call | → N10 | → N2 |
| N4 | P1 | `StatusBadge` | status→style/label map | call | — | → U7 |
| N5 | P1 | `lib/format` | `formatDate()` + title fallback | call | — | → U6, U8 |
| N10 | P3 | books router | `GET /books` → `{items: BookOut[]}` *(exists)* | call | → S1 | → N3 |

## Data Stores

| # | Place | Store | Description |
|---|-------|-------|-------------|
| S1 | P1 | `['books']` query cache | TanStack Query cache for the book list; feeds the render. Refetch on mount/focus (D3), no polling |

## Wiring diagram

```mermaid
flowchart TB
    subgraph P1["P1: Library (/) — frontend"]
        U1["U1: Loading"]
        U2["U2: ErrorState"]
        U3["U3: Empty"]
        subgraph BL["BookList container"]
            U4["U4: book list/grid"]
            subgraph BC["BookCard"]
                U5["U5: whole card (link)"]
                U6["U6: title (null-safe)"]
                U7["U7: StatusBadge"]
                U8["U8: created date"]
            end
        end
        N1["N1: useQuery(['books'])"]
        N2["N2: listBooks() (exists)"]
        N3["N3: request(BookList) (exists)"]
        N4["N4: status→style map"]
        N5["N5: formatDate + title fallback"]
        S1["S1: ['books'] query cache"]
    end

    subgraph P3["P3: Backend"]
        N10["N10: GET /books (exists)"]
    end

    subgraph P2["P2: Book page (/books/[id])"]
        BP["placeholder — coming soon"]
    end

    N1 --> N2
    N2 --> N3
    N3 --> N10
    N10 --> S1
    S1 -.-> N1
    N1 -.-> U1
    N1 -.-> U2
    N1 -.-> U3
    N1 -.-> U4
    U4 --> U5
    N4 -.-> U7
    N5 -.-> U6
    N5 -.-> U8
    U5 -->|navigate| P2

    classDef ui fill:#ffb6c1,stroke:#d87093,color:#000
    classDef nonui fill:#d3d3d3,stroke:#808080,color:#000
    classDef store fill:#e6e6fa,stroke:#9370db,color:#000
    class U1,U2,U3,U4,U5,U6,U7,U8 ui
    class N1,N2,N3,N4,N5,N10 nonui
    class S1 store
```

**Notes:**
- N2/N3/N10 and U1/U2/U3 (the primitives) are **existing** from Step 8 — Step 9
  reuses them; the render swap in `app/page.tsx` (N1's consumers) is the change.
- U5 wires to the **Place** P2 (navigation), not an affordance inside it — the
  book page is a placeholder until Step 10/11.
- No write path, no mutation, no polling: Library is read-only this step (D3,
  R6.x).
