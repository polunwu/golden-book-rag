"use client";

import { useQuery } from "@tanstack/react-query";
import { listBooks } from "../api/books";
import { BookCard } from "../components/BookCard";
import { Empty } from "../components/Empty";
import { ErrorState } from "../components/ErrorState";
import { Skeleton } from "../components/ui";

function LibrarySkeleton() {
  return (
    <ul className="divide-y divide-rule" aria-hidden>
      {[0, 1, 2].map((i) => (
        <li key={i} className="px-3 py-4">
          <Skeleton className="h-5 w-2/3 rounded" />
          <Skeleton className="mt-2.5 h-3 w-32 rounded" />
        </li>
      ))}
    </ul>
  );
}

export default function Library() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["books"],
    queryFn: listBooks,
  });

  const count = data?.length ?? 0;

  return (
    <section>
      <header className="mb-6">
        <h1 className="text-balance text-2xl tracking-tight text-ink">
          Your library
        </h1>
        {count > 0 && (
          <p className="mt-1 font-sans text-sm text-ink-muted">
            {count} book{count === 1 ? "" : "s"}
          </p>
        )}
      </header>

      {isLoading ? (
        <LibrarySkeleton />
      ) : error ? (
        <ErrorState detail={(error as Error).message} />
      ) : count === 0 ? (
        <Empty
          label="Your library is empty"
          hint="Books you add will appear here, ready to search and ask."
        />
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {data!.map((book) => (
            <BookCard key={book.id} book={book} />
          ))}
        </ul>
      )}
    </section>
  );
}
