---
shaping: true
---

# Step 12: Status — Breadboard (Shape A)

Detailing **Shape A** (`docs/v1/step12/shaping.md`) into concrete affordances +
wiring. Four Places: the existing **Library** (modified — shared `refetchInterval`
+ failed-card re-upload + the upload state grows a `bookId`/`title`), the existing
**Book page** (modified — processing/failed panels replace the terse `AskPanel`
notice; still un-polled), the existing **Upload Dialog** (modified — a re-upload
mode seeded with `book_id` + prefilled title), and the **Backend** (unchanged —
`GET /books`, `GET /books/{id}`, the `book_id` re-upload path all exist). Plus one
new non-UI module: `lib/status.ts`, the shared polling policy.

Affordance tables are the source of truth; the Mermaid renders them.

## Places

| # | Place | Description |
|---|-------|-------------|
| P1 | Library (`/`) — frontend | Existing `app/page.tsx`. Gains the shared `refetchInterval` on `['books']` (live badges), and holds the upload state which grows from a bare `open` boolean to `{open, bookId?, title?}` so a `failed` card can open the dialog in re-upload mode |
| P2 | Book page (`/books/[id]`) — frontend | Existing `app/books/[id]/page.tsx`. **Un-polled** (D1): reads `['book', id]` fresh on mount; picks the panel by status — `ready`→`AskPanel`, `pending`/`processing`→**processing panel** (new), `failed`→**failed panel** (new, read-only `error_message`) |
| P3 | Upload Dialog — frontend | Existing `BookUploadDialog`/`BookUploadForm`. Gains a **re-upload mode**: optional `bookId` + `initialTitle`; the mutation appends `book_id`, `onSuccess` invalidates `['books']` (+ `['book', id]`) |
| P4 | Backend | `GET /books` (the polled list), `GET /books/{id}` (book-page status), `POST /books/upload` (optional `book_id` → upsert `pending`, clear `error_message`). **All exist** (R7.1) |
| — | `lib/status.ts` | **New** shared policy module: `isTerminal(status)` + a `refetchInterval` fn (poll while any observed book is non-terminal; `false` once all terminal). Not a Place — a pure helper wired into N2 |

## UI Affordances

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| U1 | P1 | `app/page.tsx` (header) | "Upload book" button (new-upload mode — no `bookId`) | click | → N3 | — |
| U2 | P1 | book list `<ul>` | `<BookCard/>` list — badges **flip live** `pending→processing→ready/failed` (no refresh) | render | — | ← N2 |
| U3 | P1 | `<BookCard/>` (status=`failed`) | **"Re-upload" affordance** (sole re-upload entry — D2) | click | → N4 | — |
| U4 | P2 | book page | **Processing panel** (`pending`/`processing`): "we're parsing/embedding — Ask unlocks when ready"; replaces `AskPanel`'s terse notice; Ask not rendered | render | — | ← N7 |
| U5 | P2 | book page | **Failed panel** (`failed`, read-only): the book's `error_message` + a pointer back via the `← Library` link to retry; **no in-page re-upload** (D2) | render | — | ← N7 |
| U6 | P2 | book page | `<AskPanel/>` (rendered **only** when `ready`) | render | — | ← N7 |
| U7 | P3 | `BookUploadForm` | title `<Input>` — **prefilled** from `initialTitle` in re-upload mode (still editable); new-upload autofill unchanged | render/type | → (form state) | ← S2 |
| U8 | P3 | `BookUploadDialog` | submit `<Button>` (existing; busy/disabled while in-flight or invalid — file still required, so re-upload stays gated until a PDF is picked) | click | → N5 | — |

## Code Affordances

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| N1 | — | `lib/status.ts` | `isTerminal(status)` + `refetchIntervalFor(books, ms=2000)` — returns `ms` while **any** book is non-terminal, `false` once all terminal (D4/R1.1). Single source of the stop rule | call | — | → N2 |
| N2 | P1 | `app/page.tsx` | `useQuery(['books'], listBooks)` gains `refetchInterval: (q) => refetchIntervalFor(q.state.data)` — **the sole polling call site** (D1/R1.2/R1.4) | observe | → N10 | → U2 |
| N3 | P1 | `app/page.tsx` | `openUpload()` — set upload state `{open:true}` (no `bookId`) | call | → S1 | — |
| N4 | P1 | `app/page.tsx` ← `<BookCard onReupload/>` | `onReupload(book)` — set upload state `{open:true, bookId:book.id, title:book.title}` (A8) | call | → S1 | — |
| N5 | P3 | `BookUploadDialog` | `mutation.mutate({file,title})` → `onSuccess`: `invalidateQueries(['books'])` (+ `['book', bookId]` when re-upload) + close. Re-entering `pending` resumes N2's polling (R4.2) | call | → N6, → N2 | — |
| N6 | P3 | `api/books.ts` | `uploadBook(file, title, bookId?)` — append `book_id` to `FormData` **only when present**; new uploads omit it (D3/R4.1) | call | → N11 | → N5 |
| N7 | P2 | `app/books/[id]/page.tsx` | `useQuery(['book', id], getBook)` — **un-polled** (no `refetchInterval`), fresh on mount; **picks** U4/U5/U6 by `book.status` (D1/R1.3) | observe | → N12 | → U4/U5/U6 |
| N10 | P4 | `routers/books.py` | `GET /books` (newest-first) — the polled list *(exists)* | call | → S3 (read) | → N2 |
| N11 | P4 | `routers/books.py` | `POST /books/upload` w/ optional `book_id` — `422` non-UUID, `404` unknown, else upsert `status='pending', error_message=NULL` + re-schedule ingest, `202` *(exists)* | call | → S3, → N13 | → N6 |
| N12 | P4 | `routers/books.py` | `GET /books/{id}` → `BookOut` (status + error_message) *(exists)* | call | → S3 (read) | → N7 |
| N13 | P4 | `services/ingest.py` | `run_ingest` BackgroundTask — drives the `books.status` lifecycle (out of scope; Step 12 watches it via the poll) *(exists)* | call | → S3 | — |

## Data Stores

| # | Place | Store | Description |
|---|-------|-------|-------------|
| S1 | P1 | upload state `{open: boolean, bookId?: string, title?: string\|null}` | Was a bare `open` boolean (Step 11). New-upload (N3) sets `{open:true}`; re-upload (N4) seeds `bookId`+`title`. Read by P3 to `showModal()` and seed the form |
| S2 | P3 | `initialTitle` (string \| null) prop | Derived from S1's `title`; seeds `BookUploadForm`'s default title in re-upload mode (U7). New-upload: undefined → empty, autofill unchanged |
| S3 | P4 | `books` table (status lifecycle) | `status`/`error_message` written by N13 (`pending→processing→ready/failed`); read by N10 (list poll) and N12 (book page). The single source the live badges + panels reflect |
| — | P3 | `mutation.isPending` / `mutation.error` | Existing Step 11 stores (busy/disabled + inline server error) — reused unchanged, not re-listed |

## Wiring

```mermaid
flowchart TB
    status["lib/status.ts<br/>N1: isTerminal + refetchIntervalFor"]

    subgraph P1["P1: Library (/)"]
        U1["U1: 'Upload book' (new)"]
        U2["U2: BookCard list — badges flip LIVE"]
        U3["U3: failed card 'Re-upload'"]
        N2["N2: useQuery(['books'], refetchInterval)"]
        N3["N3: openUpload() (no bookId)"]
        N4["N4: onReupload(book) — seed bookId+title"]
        S1["S1: upload state {open,bookId?,title?}"]
    end

    subgraph P2["P2: Book page (/books/[id]) — UN-POLLED"]
        U4["U4: Processing panel"]
        U5["U5: Failed panel (error_message)"]
        U6["U6: AskPanel (ready only)"]
        N7["N7: useQuery(['book', id]) — no interval; picks panel"]
    end

    subgraph P3["P3: Upload Dialog (re-upload mode)"]
        U7["U7: title input (prefilled)"]
        U8["U8: submit (file still required)"]
        N5["N5: mutate → onSuccess invalidate + close"]
        N6["N6: uploadBook(file,title,bookId?)"]
        S2["S2: initialTitle"]
    end

    subgraph P4["P4: Backend (all exist)"]
        N10["N10: GET /books (polled)"]
        N11["N11: POST /books/upload (book_id path)"]
        N12["N12: GET /books/{id}"]
        N13["N13: run_ingest (status lifecycle)"]
        S3["S3: books table (status/error_message)"]
    end

    %% shared policy → library poll
    status --> N2
    N2 --> N10
    N10 --> S3
    S3 -.-> N10
    N10 -.-> N2
    N2 -.->|live| U2

    %% open dialog (new vs re-upload)
    U1 --> N3
    U3 --> N4
    N3 --> S1
    N4 --> S1
    S1 -.->|showModal + seed| P3
    S1 -.-> S2
    S2 -.-> U7

    %% submit → upload → re-enter pending → re-poll
    U8 --> N5
    N5 --> N6
    N6 --> N11
    N11 --> S3
    N11 --> N13
    N13 --> S3
    N11 -.->|202| N6
    N5 -.->|invalidate ['books']/['book',id]| N2
    N5 -.-> N7

    %% book page reads status, picks panel
    N7 --> N12
    N12 --> S3
    S3 -.-> N12
    N12 -.-> N7
    N7 -.->|ready| U6
    N7 -.->|pending/processing| U4
    N7 -.->|failed| U5

    classDef ui fill:#ffb6c1,stroke:#d87093,color:#000
    classDef nonui fill:#d3d3d3,stroke:#808080,color:#000
    classDef store fill:#e6e6fa,stroke:#9370db,color:#000
    class U1,U2,U3,U4,U5,U6,U7,U8 ui
    class N1,N2,N3,N4,N5,N6,N7,N10,N11,N12,N13 nonui
    class S1,S2,S3 store
    class status nonui
```

## Verification

- **Every U displays/acts with a source.** U2 (live badges) ← N2 (polled
  `['books']`); U4/U5/U6 ← N7's status pick; U7 (prefilled title) ← S2 ← S1.
  U1/U3/U8 are pure inputs.
- **Every N connects.** N1→N2; N2→N10/→U2; N3→S1; N4→S1; N5→N6/→N2(+N7 invalidate);
  N6→N11; N7→N12/→U4/U5/U6; N10→S3→N2; N11→S3/N13; N12→S3→N7; N13→S3.
- **Every S is read.** S1 (P3 showModal + seed; also feeds S2), S2 (U7),
  S3 (N10 list poll, N12 book page).
- **The stop rule lives in one place** (D4): N1's `refetchIntervalFor` returns
  `false` once every observed book is terminal — N2 is the only consumer, so the
  cross-cutting "stop polling at terminal states" is a single `return false`. No
  `setInterval`/`useEffect` timer anywhere (R1.4).
- **The book page does not poll and does not mutate** (D1/D2): N7 has no
  `refetchInterval`; it only *reads* and *picks* a panel. The live flip is watched
  on P1. Re-upload (N4/N5) is library-only; a `failed` book page (U5) points back
  to P1 to retry.
- **Re-upload re-enters the polling loop**: N5's `invalidateQueries(['books'])`
  refetches the now-`pending` row, which makes N1's policy return an interval
  again → N2 resumes polling until the re-ingest reaches a terminal state.
- **`book_id` is conditional** (D3): N6 appends it only in re-upload mode; the
  Step 11 new-upload `FormData` is byte-for-byte unchanged.

## Proposed slices (full breakdown → `slices.md`)

| # | Slice | Parts | Affordances | Demo |
|---|-------|-------|-------------|------|
| V1 | **Live library polling** | A1, A2 | U2; N1, N2, N10 *(exists)*, N13 *(exists)*, S3 | Upload a real PDF → its library card flips `pending→processing→ready` **live with no refresh**; polling stops once all cards are terminal |
| V2 | **Processing/failed panels + re-upload** | A3, A4, A5, A6, A7, A8 | U1, U3, U4, U5, U6, U7, U8; N3, N4, N5, N6, N7, N11 *(exists)*, N12 *(exists)*; S1, S2 | Open a `processing` book → processing panel, Ask disabled. Force a `failed` book → book page shows its `error_message` (read-only); its **library card** offers **Re-upload** → dialog opens prefilled → pick the PDF → submit → card flips back to `pending` and polls live |
| V3 | **`impeccable` pass** | A9 | (no new affordances — polish over V1+V2) | The processing + failed panels, the failed-card re-upload affordance, and smooth (non-jarring) live badge transitions |

V2 carries the book-page panels and the re-upload path; V1 ships the live poll on
its own (a real upload flips to `ready` without a refresh) so each slice demos
against the running backend. V1's polling immediately makes V2's re-uploaded card
visibly re-enter `pending` and march to `ready`.

## Next Step

Write `slices.md` (per-slice affordance tables + demo statements) from the V1–V3
proposal above, then `V1-plan.md`. No flagged unknowns — every affordance is
ordinary TanStack Query config (`refetchInterval`) + presentational panels over
the existing `['books']`/`['book', id]` queries, the unchanged backend, and the
Step 11 dialog/badge/schema.
