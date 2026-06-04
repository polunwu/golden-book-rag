export function Empty({
  label = "Nothing here yet.",
  hint,
}: {
  label?: string;
  hint?: string;
}) {
  return (
    <div className="py-20 text-center">
      <p className="text-lg text-ink">{label}</p>
      {hint && <p className="mt-1.5 font-sans text-sm text-ink-muted">{hint}</p>}
    </div>
  );
}
