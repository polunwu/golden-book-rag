import type { BookStatus } from "@/api/schemas/book";
import { StatusPanel } from "./StatusPanel";

// Shown on the book page while ingest runs (pending/processing). Replaces the
// terse AskPanel notice; the live flip to ready is watched on the library.
export function ProcessingPanel({ status }: { status: BookStatus }) {
  const verb = status === "pending" ? "queued for processing" : "being processed";
  return (
    <StatusPanel
      heading={`This book is ${verb}`}
      dot={
        <span className="relative inline-flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-processing opacity-60" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-status-processing" />
        </span>
      }
    >
      <p className="mt-2 max-w-prose font-sans text-sm leading-relaxed text-ink-muted">
        We&rsquo;re parsing the PDF and embedding its pages. Ask unlocks once
        it&rsquo;s ready; watch the status flip on your library shelf.
      </p>
    </StatusPanel>
  );
}
