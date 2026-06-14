"use client";

import { useAuthed } from "@/lib/session";

// Passive mode read-out for the app header. Reports guest vs admin; never
// toggles — switching modes happens only at /auth (undiscoverable route).
export function AuthIndicator() {
  const authed = useAuthed();
  if (!authed) {
    return <span className="font-sans text-xs text-ink-muted">Guest mode</span>;
  }
  // Admin mode unlocks writes — the privileged state earns the dot+label idiom
  // (an ink dot, not a status color, which stays reserved for book status).
  return (
    <span className="inline-flex items-center gap-1.5 font-sans text-xs font-medium text-ink">
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-ink" />
      Admin mode
    </span>
  );
}
