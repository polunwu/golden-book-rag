"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { BookStatus } from "@/api/schemas/book";
import { ask } from "@/api/books";
import { AnswerView } from "@/components/AnswerView";
import { ErrorState } from "@/components/ErrorState";
import { Button, Input, Notice } from "@/components/ui";

export function AskPanel({
  bookId,
  status,
}: {
  bookId: string;
  status: BookStatus;
}) {
  const [query, setQuery] = useState("");
  const ready = status === "ready";

  const mutation = useMutation({
    mutationFn: (q: string) => ask(bookId, { query: q, k: 5 }, true),
  });

  const canSubmit = ready && query.trim().length > 0 && !mutation.isPending;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    mutation.mutate(query.trim());
  }

  return (
    <div className="mt-6">
      {!ready && (
        <Notice className="mb-4">
          This book is <span className="font-medium text-ink">{status}</span> —
          ask is available once it&rsquo;s ready.
        </Notice>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row">
        <Input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={!ready}
          placeholder="Ask a question about this book…"
          className="flex-1"
        />
        <Button type="submit" disabled={!canSubmit}>
          {mutation.isPending ? "Asking…" : "Ask"}
        </Button>
      </form>

      {mutation.error && (
        <div className="mt-4">
          <ErrorState detail={(mutation.error as Error).message} />
        </div>
      )}

      {mutation.data && (
        <AnswerView
          answer={mutation.data.answer}
          refused={mutation.data.refused}
          citations={mutation.data.citations}
        />
      )}
    </div>
  );
}
