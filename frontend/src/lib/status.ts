import type { BookOut, BookStatus } from "@/api/schemas/book";

// Terminal = ingest is done (succeeded or failed) — no further status change is
// coming, so there is nothing left to poll for.
const TERMINAL: ReadonlySet<BookStatus> = new Set(["ready", "failed"]);

export function isTerminal(status: BookStatus): boolean {
  return TERMINAL.has(status);
}

// The single source of the "when to poll / when to stop" rule. Poll while ANY
// observed book is still non-terminal; stop (false) once every book is terminal
// — or when there are no books to watch. Fed to the ['books'] useQuery's
// refetchInterval, so the stop is a plain `return false`, no manual timer.
export function refetchIntervalFor(
  books: BookOut[] | undefined,
  ms = 10000,
): number | false {
  if (!books?.length) return false;
  return books.some((b) => !isTerminal(b.status)) ? ms : false;
}
