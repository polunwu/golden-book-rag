export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="font-sans text-sm text-ink-muted" role="status">
      {label}
    </p>
  );
}
