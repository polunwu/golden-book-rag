export function ErrorState({ detail }: { detail: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-rule bg-paper-raised px-4 py-3.5"
    >
      <p className="flex items-center gap-2 font-sans text-sm font-medium text-ink">
        <span className="inline-block h-2 w-2 rounded-full bg-status-failed" />
        Something went wrong
      </p>
      <p className="mt-1 font-sans text-sm text-ink-muted">{detail}</p>
    </div>
  );
}
