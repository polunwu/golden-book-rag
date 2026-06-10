export function Empty({
  label = "Nothing here yet.",
  hint,
  action,
}: {
  label?: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="py-20 text-center">
      <p className="text-lg text-ink">{label}</p>
      {hint && <p className="mt-1.5 font-sans text-sm text-ink-muted">{hint}</p>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}
