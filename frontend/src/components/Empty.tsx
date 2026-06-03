export function Empty({ label = "Nothing here yet." }: { label?: string }) {
  return <p className="text-sm text-zinc-500">{label}</p>;
}
