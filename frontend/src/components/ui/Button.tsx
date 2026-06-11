// Action button: `primary` (ink fill) or `danger` (failed-red fill for
// destructive confirms). The focus ring stays the app-wide processing amber for
// both — a red ring on the red fill would be near-invisible and breaks the
// single focus-color vocabulary; the fill already carries the danger signal.
const VARIANTS = {
  primary: "border-ink bg-ink text-paper",
  danger: "border-status-failed bg-status-failed text-paper",
} as const;

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ComponentProps<"button"> & { variant?: keyof typeof VARIANTS }) {
  return (
    <button
      className={`cursor-pointer rounded-lg border px-5 py-2.5 font-sans text-sm font-medium transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
