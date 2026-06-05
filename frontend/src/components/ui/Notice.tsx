// Muted status panel (gate notices, refusals); for failures use <ErrorState/>.
export function Notice({
  children,
  role = "status",
  className = "",
}: {
  children: React.ReactNode;
  role?: string;
  className?: string;
}) {
  return (
    <p
      role={role}
      className={`rounded-lg border border-rule bg-paper-raised px-4 py-3 font-sans text-sm text-ink-muted ${className}`}
    >
      {children}
    </p>
  );
}
