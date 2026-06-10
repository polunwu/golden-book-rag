// Shared shell for the book-page status surfaces (processing/failed): the
// bordered raised card + a dot-and-heading row. Each caller supplies its own
// dot node, heading, and body so the chrome lives in one place.
export function StatusPanel({
  dot,
  heading,
  role,
  children,
}: {
  dot: React.ReactNode;
  heading: string;
  role?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      role={role}
      className="mt-8 rounded-lg border border-rule bg-paper-raised px-5 py-6"
    >
      <p className="flex items-center gap-2.5 font-sans text-sm font-medium text-ink">
        {dot}
        {heading}
      </p>
      {children}
    </div>
  );
}
