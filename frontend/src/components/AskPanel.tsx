"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { BookStatus } from "@/api/schemas/book";
import { ask } from "@/api/books";
import { AnswerView } from "@/components/AnswerView";
import { ErrorState } from "@/components/ErrorState";
import { Button, Input, Notice, Skeleton } from "@/components/ui";

// One column's worth of loading placeholder — prose lines + two faux source
// cards, mirroring the real answer layout so the resolve doesn't reflow.
function AnswerSkeleton() {
  return (
    <div aria-hidden>
      <div className="space-y-2.5">
        <Skeleton className="h-4 w-full rounded" />
        <Skeleton className="h-4 w-[92%] rounded" />
        <Skeleton className="h-4 w-[78%] rounded" />
      </div>
      <div className="mt-8 space-y-3">
        <Skeleton className="h-20 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    </div>
  );
}

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

  const toggleEnabled = ready && !mutation.isPending;

  return (
    <div className="mt-8">
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
        <Button type="submit" disabled={!canSubmit} className="shrink-0">
          {mutation.isPending ? "Asking…" : "Ask"}
        </Button>
      </form>

      <label
        className={`mt-4 inline-flex select-none items-center gap-2.5 font-sans text-sm ${
          toggleEnabled
            ? "cursor-pointer text-ink-muted"
            : "cursor-not-allowed text-ink-muted/50"
        }`}
      >
        <input
          type="checkbox"
          checked={compare}
          onChange={(e) => setCompare(e.target.checked)}
          disabled={!toggleEnabled}
          className="peer sr-only"
        />
        <span className="relative h-4 w-7 shrink-0 rounded-full bg-rule transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-3 after:w-3 after:rounded-full after:bg-paper after:shadow-sm after:transition-transform after:content-[''] peer-checked:bg-status-processing peer-checked:after:translate-x-3 peer-focus-visible:ring-2 peer-focus-visible:ring-status-processing peer-focus-visible:ring-offset-1 peer-focus-visible:ring-offset-paper peer-disabled:opacity-50" />
        Compare with a plain LLM (no retrieval)
      </label>

      {mutation.error && (
        <div className="mt-6">
          <ErrorState detail={(mutation.error as Error).message} />
        </div>
      )}

      {mutation.isPending ? (
        compare ? (
          <CompareGrid
            retrieval={<AnswerSkeleton />}
            plain={<AnswerSkeleton />}
          />
        ) : (
          <div className="mt-8">
            <AnswerSkeleton />
          </div>
        )
      ) : (
        mutation.data &&
        (mutation.data.plain ? (
          <CompareGrid
            retrieval={
              <AnswerView
                answer={mutation.data.rag.answer}
                refused={mutation.data.rag.refused}
                citations={mutation.data.rag.citations}
              />
            }
            plain={
              <AnswerView
                answer={mutation.data.plain.answer}
                refused={mutation.data.plain.refused}
                citations={mutation.data.plain.citations}
              />
            }
          />
        ) : (
          <div className="mt-8">
            <AnswerView
              answer={mutation.data.rag.answer}
              refused={mutation.data.rag.refused}
              citations={mutation.data.rag.citations}
            />
          </div>
        ))
      )}
    </div>
  );
}

// Two peer columns. On lg the grid breaks out of the page's reading column to a
// wider band so full-text citation cards breathe; below lg it stacks (grounded
// column first). The header dot/label carries the grounded-vs-plain signal.
function CompareGrid({
  retrieval,
  plain,
}: {
  retrieval: React.ReactNode;
  plain: React.ReactNode;
}) {
  return (
    <div className="mt-8 lg:mx-[calc(50%-50vw)] lg:px-5">
      <div className="grid gap-y-10 lg:mx-auto lg:max-w-6xl lg:grid-cols-2">
        <section className="lg:pr-12">
          <h2 className="mb-4 font-sans text-xs font-semibold uppercase tracking-[0.08em] text-ink">
            With retrieval
          </h2>
          {retrieval}
        </section>
        <section className="lg:border-l lg:border-rule lg:pl-12">
          <h2 className="mb-4 font-sans text-xs font-semibold uppercase tracking-[0.08em] text-ink-muted">
            Without retrieval
          </h2>
          {plain}
        </section>
      </div>
    </div>
  );
}
