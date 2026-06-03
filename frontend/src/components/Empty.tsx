// Defined now (R4.2) for reuse in Steps 9+; the smoke doesn't render it.
export function Empty({ label = "Nothing here yet." }: { label?: string }) {
  return <p className="text-sm text-zinc-500">{label}</p>;
}
