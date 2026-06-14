import Link from "next/link";
import { RotateCcw } from "lucide-react";
import type { BookOut } from "@/api/schemas/book";
import { bookTitle, formatDate } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

export function BookCard({
  book,
  onReupload,
  canWrite = false,
}: {
  book: BookOut;
  onReupload?: (book: BookOut) => void;
  canWrite?: boolean;
}) {
  const canReupload = canWrite && book.status === "failed" && Boolean(onReupload);

  return (
    // Row so the failed-card Re-upload sits at the right, vertically centered,
    // as a sibling of the nav <Link> (outside it: no nested interactive). The
    // hover tint lives on the <li> so the whole row (incl. the button strip)
    // highlights as one; the arrow still reveals only on the link's own hover.
    <li className="group/row flex items-stretch transition-colors hover:bg-paper-raised has-[a:active]:bg-paper-raised/70">
      <Link
        href={`/books/${book.id}`}
        className="group/link block min-w-0 flex-1 px-3 py-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-inset"
      >
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="min-w-0 text-balance break-words text-lg leading-snug text-ink">
            {bookTitle(book)}
          </h2>
          {!canReupload && (
            <span
              aria-hidden
              className="font-sans text-ink-muted opacity-0 transition-all duration-200 ease-out group-hover/link:translate-x-0.5 group-hover/link:opacity-100 group-focus-visible/link:opacity-100"
            >
              &rarr;
            </span>
          )}
        </div>
        <div className="mt-1.5 flex items-center gap-2">
          <StatusBadge status={book.status} />
          <span aria-hidden className="text-xs text-ink-muted/40">
            &middot;
          </span>
          <time dateTime={book.created_at} className="font-sans text-xs text-ink-muted">
            {formatDate(book.created_at)}
          </time>
        </div>
      </Link>
      {/* Sole retry entry for a failed book (the book page is read-only). Label
          collapses to icon-only on the narrowest screens. */}
      {canReupload && (
        <div className="flex shrink-0 items-center py-3 pl-2 pr-3">
          <button
            type="button"
            onClick={() => onReupload?.(book)}
            aria-label="Re-upload"
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-rule bg-paper px-3 py-2 font-sans text-xs font-medium text-ink transition-colors hover:bg-paper-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
          >
            <RotateCcw aria-hidden className="h-3.5 w-3.5 text-ink-muted" />
            <span className="hidden sm:inline">Re-upload</span>
          </button>
        </div>
      )}
    </li>
  );
}
