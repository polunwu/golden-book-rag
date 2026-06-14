"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { deleteBook, getBook } from "@/api/books";
import type { BookOut } from "@/api/schemas/book";
import { AskPanel } from "@/components/books/AskPanel";
import { FailedPanel } from "@/components/books/FailedPanel";
import { ProcessingPanel } from "@/components/books/ProcessingPanel";
import { StatusBadge } from "@/components/books/StatusBadge";
import { ConfirmDialog, ErrorState, Skeleton } from "@/components/ui";
import { bookTitle } from "@/lib/format";
import { useAuthed } from "@/lib/session";

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
  const canWrite = useAuthed();
  const qc = useQueryClient();
  const router = useRouter();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleted, setDeleted] = useState(false);

  const { data: book, isLoading, error } = useQuery({
    queryKey: ["book", id],
    queryFn: () => getBook(id),
  });

  // Optimistically drop the book from the library list, then navigate there;
  // on failure restore the list and keep the user here with the error in the
  // dialog. `replace` (not push) so Back doesn't return to the now-gone book.
  const del = useMutation({
    mutationFn: () => deleteBook(id),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ["books"] });
      const prev = qc.getQueryData<BookOut[]>(["books"]);
      qc.setQueryData<BookOut[]>(["books"], (old) =>
        old?.filter((b) => b.id !== id),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["books"], ctx.prev);
    },
    onSuccess: () => {
      // Show the success tick, then hand off to the library. The stale
      // ['book', id] entry GCs after unmount; removing it here would yank data
      // from the still-mounted page (a doomed 404 refetch + skeleton flash).
      setDeleted(true);
      setTimeout(() => router.replace("/"), 800);
    },
  });

  const openConfirm = () => {
    del.reset();
    setDeleted(false);
    setConfirmOpen(true);
  };

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
            <header className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1.5">
                <h1 className="text-balance text-3xl leading-tight tracking-tight text-ink">
                  {bookTitle(book!)}
                </h1>
                <StatusBadge status={book!.status} />
              </div>
              {canWrite && (
                <button
                  type="button"
                  onClick={openConfirm}
                  aria-label="Delete book"
                  className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border border-rule bg-paper px-3 py-2 font-sans text-xs font-medium text-ink-muted transition-colors hover:border-status-failed/40 hover:bg-status-failed/5 hover:text-status-failed focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
                >
                  <Trash2 aria-hidden className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Delete</span>
                </button>
              )}
            </header>
            {book!.status === "ready" ? (
              <AskPanel key={id} bookId={id} status={book!.status} />
            ) : book!.status === "failed" ? (
              <FailedPanel errorMessage={book!.error_message} />
            ) : (
              <ProcessingPanel status={book!.status} />
            )}

            <ConfirmDialog
              open={confirmOpen}
              title="Delete this book?"
              body={
                <>
                  <span className="font-medium text-ink">
                    {bookTitle(book!)}
                  </span>{" "}
                  and its uploaded PDF will be permanently deleted. This
                  can&apos;t be undone.
                </>
              }
              confirmLabel="Delete"
              busyLabel="Deleting…"
              destructive
              busy={del.isPending}
              error={del.error ? (del.error as Error).message : null}
              success={deleted}
              successLabel="Deleted"
              successHint="Taking you to your library…"
              onConfirm={() => del.mutate()}
              onCancel={() => setConfirmOpen(false)}
            />
          </>
        )}
      </div>
    </section>
  );
}
