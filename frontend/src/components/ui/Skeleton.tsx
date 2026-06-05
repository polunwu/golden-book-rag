// Pulsing placeholder block; size + rounding come from `className`.
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-rule ${className}`} />;
}
