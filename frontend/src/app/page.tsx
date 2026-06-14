"use client";

import { useState } from "react";
import { Upload } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { listBooks } from "@/api/books";
import type { BookOut } from "@/api/schemas/book";
import { refetchIntervalFor } from "@/lib/status";
import { useAuthed } from "@/lib/session";
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
  const canWrite = useAuthed();
  const { data, isLoading, error } = useQuery({
    queryKey: ["books"],
    queryFn: listBooks,
    refetchInterval: (query) => refetchIntervalFor(query.state.data),
  });

  // Upload modal state: a fresh upload carries no id; a re-upload seeds the
  // failed book's id + title (the dialog's re-upload mode).
  const [upload, setUpload] = useState<{
    open: boolean;
    bookId?: string;
    title?: string | null;
  }>({ open: false });

  const openUpload = () => setUpload({ open: true });
  const closeUpload = () => setUpload((u) => ({ ...u, open: false }));
  const onReupload = (book: BookOut) =>
    setUpload({ open: true, bookId: book.id, title: book.title });

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
        {canWrite && (
          <Button
            onClick={openUpload}
            className="flex shrink-0 items-center gap-2"
          >
            <Upload aria-hidden className="h-4 w-4" />
            Upload book
          </Button>
        )}
      </header>

      {isLoading ? (
        <LibrarySkeleton />
      ) : error ? (
        <ErrorState detail={(error as Error).message} />
      ) : count === 0 ? (
        <Empty
          label="Your library is empty"
          hint={
            canWrite
              ? "Books you add will appear here, ready to search and ask."
              : "No books are available yet."
          }
          action={
            canWrite ? <Button onClick={openUpload}>Upload book</Button> : undefined
          }
        />
      ) : (
        <ul className="divide-y divide-rule border-y border-rule">
          {data!.map((book) => (
            <BookCard
              key={book.id}
              book={book}
              onReupload={onReupload}
              canWrite={canWrite}
            />
          ))}
        </ul>
      )}

      <BookUploadDialog
        open={upload.open}
        onClose={closeUpload}
        bookId={upload.bookId}
        initialTitle={upload.title}
      />
    </section>
  );
}
