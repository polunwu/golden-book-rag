"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Element, Root, RootContent, Text } from "hast";
import type { Citation } from "@/api/books";
import { Citations } from "@/components/books/Citations";

// A citation token may group several sources — the model emits `[1]` but also
// `[1, 2]`. We can't parse these from the raw answer string anymore (Markdown
// owns that), so a rehype plugin walks the rendered tree and swaps each marker
// run inside a text node for a `<cite>` element carrying the numbers; the `cite`
// component override below renders the interactive chips.
const MARKER_RE = /\[([\d\s,]+)\]/g;

function splitTextNode(value: string): RootContent[] {
  const out: RootContent[] = [];
  let last = 0;
  for (const m of value.matchAll(MARKER_RE)) {
    const nums = m[1].match(/\d+/g);
    if (!nums) continue;
    const start = m.index ?? 0;
    if (start > last) {
      out.push({ type: "text", value: value.slice(last, start) } as Text);
    }
    out.push({
      type: "element",
      tagName: "cite",
      properties: { markers: nums.join(",") },
      children: [],
    } as Element);
    last = start + m[0].length;
  }
  if (!out.length) return [{ type: "text", value } as Text];
  if (last < value.length) {
    out.push({ type: "text", value: value.slice(last) } as Text);
  }
  return out;
}

// Markers inside code (`arr[1]`, fenced blocks) are literal, not citations —
// don't descend into these and don't rewrite their text.
const CODE_TAGS = new Set(["code", "pre"]);

function rehypeCitations() {
  return (tree: Root) => {
    const walk = (node: Root | Element) => {
      if (!("children" in node) || !node.children) return;
      const next: RootContent[] = [];
      for (const child of node.children) {
        if (child.type === "text") {
          next.push(...splitTextNode(child.value));
        } else {
          if (child.type === "element" && !CODE_TAGS.has(child.tagName)) {
            walk(child);
          }
          next.push(child);
        }
      }
      node.children = next;
    };
    walk(tree);
  };
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

  const components = useMemo<Components>(
    () => ({
      p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
      ul: ({ children }) => (
        <ul className="mb-4 list-disc space-y-1.5 pl-6 last:mb-0">{children}</ul>
      ),
      ol: ({ children }) => (
        <ol className="mb-4 list-decimal space-y-1.5 pl-6 last:mb-0">
          {children}
        </ol>
      ),
      li: ({ children }) => <li className="leading-[1.7]">{children}</li>,
      strong: ({ children }) => (
        <strong className="font-semibold text-ink">{children}</strong>
      ),
      em: ({ children }) => <em className="italic">{children}</em>,
      a: ({ children, href }) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-status-processing underline underline-offset-2"
        >
          {children}
        </a>
      ),
      h1: ({ children }) => (
        <h3 className="mb-3 mt-6 font-sans text-lg font-semibold text-ink first:mt-0">
          {children}
        </h3>
      ),
      h2: ({ children }) => (
        <h3 className="mb-3 mt-6 font-sans text-lg font-semibold text-ink first:mt-0">
          {children}
        </h3>
      ),
      h3: ({ children }) => (
        <h4 className="mb-2 mt-5 font-sans text-base font-semibold text-ink first:mt-0">
          {children}
        </h4>
      ),
      blockquote: ({ children }) => (
        <blockquote className="my-4 border-l-2 border-rule pl-4 italic text-ink-muted">
          {children}
        </blockquote>
      ),
      hr: () => <hr className="my-6 border-rule" />,
      pre: ({ children }) => (
        <pre className="mb-4 overflow-x-auto rounded-lg bg-paper-raised p-3 font-mono text-sm last:mb-0">
          {children}
        </pre>
      ),
      code: ({ className, children }) =>
        /language-/.test(className ?? "") ? (
          <code className={className}>{children}</code>
        ) : (
          <code className="rounded bg-paper-raised px-1 py-0.5 font-mono text-[0.875em]">
            {children}
          </code>
        ),
      cite: ({ node }) => {
        const markers = String(node?.properties?.markers ?? "")
          .split(",")
          .map(Number)
          .filter((n) => !Number.isNaN(n));
        return (
          <span className="whitespace-nowrap">
            {markers.map((m, j) =>
              hasCitation(m) ? (
                <button
                  key={j}
                  type="button"
                  onClick={() => goToCitation(m)}
                  className="mx-0.5 inline-flex h-[1.15em] min-w-[1.15em] items-center justify-center rounded bg-status-processing/15 px-1 align-text-top font-sans text-[0.7rem] font-semibold leading-none text-status-processing transition-colors hover:bg-status-processing/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper"
                  aria-label={`Jump to source ${m}`}
                >
                  {m}
                </button>
              ) : (
                <span key={j}>[{m}]</span>
              ),
            )}
          </span>
        );
      },
    }),
    [goToCitation, hasCitation],
  );

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

      <div className="text-[1.0625rem] leading-[1.75] text-ink">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeCitations]}
          components={components}
        >
          {answer}
        </ReactMarkdown>
      </div>

      <Citations
        citations={citations}
        highlighted={highlighted}
        registerRef={registerRef}
      />
    </div>
  );
}
