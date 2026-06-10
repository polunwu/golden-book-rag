"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadBook } from "@/api/books";
import { BookUploadForm } from "./BookUploadForm";

export function BookUploadDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  // Drive the native modal from React `open`; the <dialog> `onClose` syncs
  // Esc/native closes back so state never desyncs.
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    else if (!open && d.open) d.close();
  }, [open]);

  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: ({ file, title }: { file: File; title: string }) =>
      uploadBook(file, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["books"] });
      onClose();
    },
  });

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      // A click whose target is the dialog itself (not its children) is a
      // backdrop click — close on it.
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-rule bg-paper p-6 text-ink backdrop:bg-ink/20"
    >
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-lg tracking-tight text-ink">Upload a book</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mr-1 -mt-1 rounded-md p-1 font-sans text-xl leading-none text-ink-muted transition-opacity hover:opacity-70 focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing"
        >
          ×
        </button>
      </div>
      {/* Remount per open so a reopened dialog starts with empty fields. */}
      <BookUploadForm
        key={String(open)}
        onSubmit={(file, title) => m.mutate({ file, title })}
      />
    </dialog>
  );
}
