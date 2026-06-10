import { StatusPanel } from "./StatusPanel";

// Read-only failed state on the book page: surface the ingest error and point
// back to the library to retry. Re-upload itself is library-only (the failed
// card), so there is no action here.
export function FailedPanel({ errorMessage }: { errorMessage?: string | null }) {
  return (
    <StatusPanel
      role="alert"
      heading="Processing failed"
      dot={
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-status-failed" />
      }
    >
      <p className="mt-2 max-w-prose font-sans text-sm leading-relaxed text-ink-muted">
        {errorMessage?.trim() || "Something went wrong while processing this book."}
      </p>
      <p className="mt-3 font-sans text-sm leading-relaxed text-ink-muted">
        Return to your library to re-upload the file and try again.
      </p>
    </StatusPanel>
  );
}
