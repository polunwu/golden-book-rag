"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation } from "@/api/books";
import { Citations } from "@/components/books/Citations";

// Split on a citation token, which may group several sources — the model emits
// `[1]` but also `[1, 2]`. The capturing group puts text at even indices and the
// bracket's inner (`"1, 2"`) at odd indices; each group expands to one chip per
// number.
type Segment = { text: string } | { markers: number[] };

function parseMarkers(answer: string): Segment[] {
  const parts = answer.split(/\[([\d\s,]+)\]/g);
  const out: Segment[] = [];
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const markers = part.match(/\d+/g)?.map(Number) ?? [];
      if (markers.length) out.push({ markers });
      else out.push({ text: `[${part}]` });
    } else if (part) {
      out.push({ text: part });
    }
  });
  return out;
}

export function AnswerView({
  answer,
  refused,
  citations,
}: {
  answer: string;
  refused: boolean;
  citations: Citation[];
}) {
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const refs = useRef(new Map<number, HTMLElement>());
  const clearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const registerRef = useCallback((marker: number, el: HTMLElement | null) => {
    if (el) refs.current.set(marker, el);
    else refs.current.delete(marker);
  }, []);

  const goToCitation = useCallback((marker: number) => {
    const el = refs.current.get(marker);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlighted(marker);
    if (clearTimer.current) clearTimeout(clearTimer.current);
    clearTimer.current = setTimeout(() => setHighlighted(null), 1200);
  }, []);

  useEffect(
    () => () => {
      if (clearTimer.current) clearTimeout(clearTimer.current);
    },
    [],
  );

  const hasCitation = useCallback(
    (marker: number) => citations.some((c) => c.marker === marker),
    [citations],
  );

  const segments = parseMarkers(answer);

  // Owns no outer margin — each caller (single column / a compare column under
  // its own heading) controls the gap above this block.
  return (
    <div>
      {refused && (
        <div
          role="status"
          className="mb-5 flex items-start gap-2.5 rounded-lg border border-rule bg-paper-raised px-4 py-3"
        >
          <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-status-pending" />
          <div className="font-sans text-sm">
            <p className="font-medium text-ink">Not grounded in this book</p>
            <p className="mt-0.5 text-ink-muted">
              There wasn&rsquo;t enough in this book to answer confidently.
            </p>
          </div>
        </div>
      )}

      <div className="whitespace-pre-wrap text-[1.0625rem] leading-[1.75] text-ink">
        {segments.map((seg, i) =>
          "text" in seg ? (
            <span key={i}>{seg.text}</span>
          ) : (
            <span key={i} className="whitespace-nowrap">
              {seg.markers.map((m, j) =>
                hasCitation(m) ? (
                  <button
                    key={j}
                    type="button"
                    onClick={() => goToCitation(m)}
                    className="mx-0.5 inline-flex h-[1.15em] min-w-[1.15em] items-center justify-center rounded px-1 align-text-top font-sans text-[0.7rem] font-semibold leading-none text-status-processing bg-status-processing/15 transition-colors hover:bg-status-processing/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper"
                    aria-label={`Jump to source ${m}`}
                  >
                    {m}
                  </button>
                ) : (
                  <span key={j}>[{m}]</span>
                ),
              )}
            </span>
          ),
        )}
      </div>

      <Citations
        citations={citations}
        highlighted={highlighted}
        registerRef={registerRef}
      />
    </div>
  );
}
