// Inline field-level validation error. Always rendered so its reserved line of
// height keeps the form from jumping as the message appears/clears; role="alert"
// stays silent while empty and announces when a message arrives.
export function FieldError({
  message,
  className = "",
}: {
  message?: string;
  className?: string;
}) {
  return (
    <p
      role="alert"
      className={`min-h-5 font-sans text-sm text-status-failed ${className}`}
    >
      {message}
    </p>
  );
}
