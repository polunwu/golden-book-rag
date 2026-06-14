"use client";

import { useAuthed } from "@/lib/session";

// Passive mode read-out for the app header. Reports guest vs admin; never
// toggles — switching modes happens only at /auth (undiscoverable route).
export function AuthIndicator() {
  const authed = useAuthed();
  return (
    <span
      className={
        authed
          ? "font-sans text-xs font-medium text-ink"
          : "font-sans text-xs text-ink-muted"
      }
    >
      {authed ? "Admin mode" : "Guest mode"}
    </span>
  );
}
