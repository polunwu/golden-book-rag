// Text input — bordered, shared focus ring.
export function Input({
  className = "",
  ...props
}: React.ComponentProps<"input">) {
  return (
    <input
      className={`rounded-lg border border-rule bg-paper px-4 py-2.5 font-sans text-sm text-ink placeholder:text-ink-muted/60 focus:border-status-processing focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    />
  );
}
