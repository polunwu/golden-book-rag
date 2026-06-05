// Primary action button — ink fill, shared focus ring.
export function Button({
  className = "",
  ...props
}: React.ComponentProps<"button">) {
  return (
    <button
      className={`rounded-lg border border-ink bg-ink px-5 py-2.5 font-sans text-sm font-medium text-paper transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
      {...props}
    />
  );
}
