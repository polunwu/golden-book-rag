import type { Citation } from "@/api/books";
import { breadcrumb, pageRange } from "@/lib/format";

// Each item registers its element via `registerRef` so an `[n]` marker click in
// <AnswerView/> can scroll to it; `highlighted` is the marker currently flashing.
export function Citations({
  citations,
  highlighted,
  registerRef,
}: {
  citations: Citation[];
  highlighted: number | null;
  registerRef: (marker: number, el: HTMLElement | null) => void;
}) {
  if (citations.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="font-sans text-xs font-semibold uppercase tracking-[0.08em] text-ink-muted">
        Sources
      </h2>
      <ol className="mt-3 space-y-3">
        {citations.map((c) => {
          const crumb = breadcrumb(c.section_path);
          const pages = pageRange(c.page_start, c.page_end);
          const isHot = highlighted === c.marker;
          return (
            <li
              key={c.marker}
              id={`cite-${c.marker}`}
              ref={(el) => registerRef(c.marker, el)}
              className={`scroll-mt-6 rounded-lg border px-4 py-3.5 transition-colors duration-300 ${
                isHot
                  ? "border-status-processing bg-status-processing/10"
                  : "border-rule bg-paper-raised hover:border-ink-muted/30"
              }`}
            >
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-status-processing/15 px-1 font-sans text-xs font-semibold text-status-processing">
                  {c.marker}
                </span>
                {crumb && (
                  <span className="font-sans text-xs font-medium text-ink">
                    {crumb}
                  </span>
                )}
                <span className="font-sans text-xs text-ink-muted">
                  {pages && <span>{pages}</span>}
                  {pages && <span aria-hidden className="mx-1.5">&middot;</span>}
                  <span>score {c.score.toFixed(2)}</span>
                </span>
              </div>
              <p className="mt-2.5 whitespace-pre-wrap text-sm leading-relaxed text-ink">
                {c.text}
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
