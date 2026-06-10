"use client";

import { useState } from "react";
import { Upload } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { listBooks } from "@/api/books";
import { BookCard } from "@/components/books/BookCard";
import { BookUploadDialog } from "@/components/books/BookUploadDialog";
import { Button, Empty, ErrorState, Skeleton } from "@/components/ui";

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

  const [open, setOpen] = useState(false);
  const count = data?.length ?? 0;

  return (
    <section>
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-balance text-2xl tracking-tight text-ink">
            Your library
          </h1>
          {count > 0 && (
            <p className="mt-1 font-sans text-sm text-ink-muted">
              {count} book{count === 1 ? "" : "s"}
            </p>
          )}
        </div>
        <Button
          onClick={() => setOpen(true)}
          className="flex shrink-0 items-center gap-2"
        >
          <Upload aria-hidden className="h-4 w-4" />
          Upload book
        </Button>
      </header>

      {isLoading ? (
        <LibrarySkeleton />
      ) : error ? (
        <ErrorState detail={(error as Error).message} />
      ) : count === 0 ? (
        <Empty
          label="Your library is empty"
          hint="Books you add will appear here, ready to search and ask."
          action={<Button onClick={() => setOpen(true)}>Upload book</Button>}
        />
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {data!.map((book) => (
            <BookCard key={book.id} book={book} />
          ))}
        </ul>
      )}

      <BookUploadDialog open={open} onClose={() => setOpen(false)} />
    </section>
  );
}
