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
  const [compare, setCompare] = useState(false);
  const ready = status === "ready";

  const mutation = useMutation({
    mutationFn: async (q: string) => {
      const body = { query: q, k: 5 };
      const [rag, plain] = await Promise.all([
        ask(bookId, body, true),
        compare ? ask(bookId, body, false) : Promise.resolve(null),
      ]);
      return { rag, plain };
    },
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

      <label className="mt-3 inline-flex items-center gap-2 font-sans text-sm text-ink-muted">
        <input
          type="checkbox"
          checked={compare}
          onChange={(e) => setCompare(e.target.checked)}
          disabled={!ready || mutation.isPending}
          className="disabled:cursor-not-allowed disabled:opacity-60"
        />
        Compare with plain LLM (no retrieval)
      </label>

      {mutation.error && (
        <div className="mt-4">
          <ErrorState detail={(mutation.error as Error).message} />
        </div>
      )}

      {mutation.data &&
        (mutation.data.plain ? (
          <div className="mt-6 grid gap-6 md:grid-cols-2">
            <section>
              <h2 className="mb-2 font-sans text-sm font-medium text-ink-muted">
                With retrieval
              </h2>
              <AnswerView
                answer={mutation.data.rag.answer}
                refused={mutation.data.rag.refused}
                citations={mutation.data.rag.citations}
              />
            </section>
            <section>
              <h2 className="mb-2 font-sans text-sm font-medium text-ink-muted">
                Without retrieval
              </h2>
              <AnswerView
                answer={mutation.data.plain.answer}
                refused={mutation.data.plain.refused}
                citations={mutation.data.plain.citations}
              />
            </section>
          </div>
        ) : (
          <AnswerView
            answer={mutation.data.rag.answer}
            refused={mutation.data.rag.refused}
            citations={mutation.data.rag.citations}
          />
        ))}
    </div>
  );
}
