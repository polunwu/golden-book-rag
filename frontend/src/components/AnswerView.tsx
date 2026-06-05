"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation } from "@/api/books";
import { Citations } from "@/components/Citations";
import { Notice } from "@/components/ui";

// Split on `[n]`; the capturing group puts text at even indices, marker
// numbers at odd indices.
function parseMarkers(answer: string): Array<{ text: string } | { marker: number }> {
  const parts = answer.split(/\[(\d+)\]/g);
  const out: Array<{ text: string } | { marker: number }> = [];
  parts.forEach((part, i) => {
    if (i % 2 === 1) out.push({ marker: Number(part) });
    else if (part) out.push({ text: part });
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

  return (
    <div className="mt-6">
      {refused && (
        <Notice className="mb-4">
          Not enough in this book to answer confidently.
        </Notice>
      )}

      <div className="whitespace-pre-wrap text-base leading-relaxed text-ink">
        {segments.map((seg, i) =>
          "text" in seg ? (
            <span key={i}>{seg.text}</span>
          ) : hasCitation(seg.marker) ? (
            <button
              key={i}
              type="button"
              onClick={() => goToCitation(seg.marker)}
              className="mx-0.5 inline-flex items-baseline rounded font-sans text-xs font-medium text-status-processing align-super hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper"
              aria-label={`Jump to source ${seg.marker}`}
            >
              [{seg.marker}]
            </button>
          ) : (
            <span key={i}>[{seg.marker}]</span>
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
