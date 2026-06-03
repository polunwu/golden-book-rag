export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="text-sm text-zinc-500">{label}</p>;
}
