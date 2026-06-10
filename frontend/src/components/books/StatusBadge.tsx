import type { BookStatus } from "@/api/schemas/book";

const STATUS: Record<BookStatus, { label: string; dot: string }> = {
  pending: { label: "Pending", dot: "bg-status-pending" },
  processing: { label: "Processing", dot: "bg-status-processing" },
  ready: { label: "Ready", dot: "bg-status-ready" },
  failed: { label: "Failed", dot: "bg-status-failed" },
};

export function StatusBadge({ status }: { status: BookStatus }) {
  const { label, dot } = STATUS[status];
  return (
    <span className="inline-flex items-center gap-1.5 font-sans text-xs text-ink-muted">
      <span className="relative inline-flex h-2 w-2">
        {status === "processing" && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${dot}`}
          />
        )}
        {/* Eased color so the live poll's pending→processing→ready flip glides
            rather than hard-cutting (reduced-motion neutralizes it globally). */}
        <span
          className={`relative inline-flex h-2 w-2 rounded-full transition-colors duration-500 ${dot}`}
        />
      </span>
      {label}
    </span>
  );
}
