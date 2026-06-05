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
      <h2 className="font-sans text-xs font-medium uppercase tracking-wide text-ink-muted">
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
              className={`scroll-mt-4 rounded-lg border px-4 py-3 transition-colors duration-300 ${
                isHot
                  ? "border-status-processing bg-status-processing/10"
                  : "border-rule bg-paper-raised"
              }`}
            >
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 font-sans text-xs text-ink-muted">
                <span className="font-medium text-ink">[{c.marker}]</span>
                {crumb && <span>{crumb}</span>}
                {pages && (
                  <>
                    {crumb && <span aria-hidden>&middot;</span>}
                    <span>{pages}</span>
                  </>
                )}
                <span aria-hidden>&middot;</span>
                <span>score {c.score.toFixed(2)}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink">
                {c.text}
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
