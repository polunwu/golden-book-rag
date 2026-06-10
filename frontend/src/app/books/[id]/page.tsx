"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getBook } from "@/api/books";
import { AskPanel } from "@/components/books/AskPanel";
import { StatusBadge } from "@/components/books/StatusBadge";
import { ErrorState, Skeleton } from "@/components/ui";
import { bookTitle } from "@/lib/format";

function BookSkeleton() {
  return (
    <div aria-hidden>
      <Skeleton className="h-8 w-2/3 rounded" />
      <Skeleton className="mt-3 h-3 w-24 rounded" />
      <Skeleton className="mt-8 h-11 w-full rounded-lg" />
      <Skeleton className="mt-4 h-5 w-56 rounded-full" />
    </div>
  );
}

// Next 16: a Client Component page reads route params via React's `use()`
// (params is a Promise). See node_modules/next/dist/docs dynamic-routes.
export default function BookDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const { data: book, isLoading, error } = useQuery({
    queryKey: ["book", id],
    queryFn: () => getBook(id),
  });

  return (
    <section>
      <Link
        href="/"
        className="inline-flex items-center gap-1 font-sans text-sm text-ink-muted transition-colors hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
      >
        &larr; Library
      </Link>

      <div className="mt-4">
        {isLoading ? (
          <BookSkeleton />
        ) : error ? (
          <ErrorState detail={(error as Error).message} />
        ) : (
          <>
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
              <h1 className="text-balance text-3xl leading-tight tracking-tight text-ink">
                {bookTitle(book!)}
              </h1>
              <StatusBadge status={book!.status} />
            </header>
            <AskPanel key={id} bookId={id} status={book!.status} />
          </>
        )}
      </div>
    </section>
  );
}
