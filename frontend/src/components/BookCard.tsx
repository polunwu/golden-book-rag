import Link from "next/link";
import type { BookOut } from "../api/schemas/book";
import { bookTitle, formatDate } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

export function BookCard({ book }: { book: BookOut }) {
  return (
    <li>
      <Link
        href={`/books/${book.id}`}
        className="group block px-3 py-4 transition-colors hover:bg-paper-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-2 focus-visible:ring-offset-paper active:bg-paper-raised/70"
      >
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-balance text-lg leading-snug text-ink">
            {bookTitle(book)}
          </h2>
          <span
            aria-hidden
            className="font-sans text-ink-muted opacity-0 transition-all duration-200 ease-out group-hover:translate-x-0.5 group-hover:opacity-100 group-focus-visible:opacity-100"
          >
            &rarr;
          </span>
        </div>
        <div className="mt-1.5 flex items-center gap-2">
          <StatusBadge status={book.status} />
          <span aria-hidden className="text-xs text-rule">
            &middot;
          </span>
          <time dateTime={book.created_at} className="font-sans text-xs text-ink-muted">
            {formatDate(book.created_at)}
          </time>
        </div>
      </Link>
    </li>
  );
}
