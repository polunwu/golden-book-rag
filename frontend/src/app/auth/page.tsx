"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearSecret, setSecret, useAuthed } from "@/lib/session";
import { Button, Input } from "@/components/ui";

// Undiscoverable route: nothing in the UI links here. The owner reaches it by
// typing /auth. The secret travels in a header (never the URL), and this is the
// only place the mode is switched, both ways.
export default function AuthPage() {
  const authed = useAuthed();
  const router = useRouter();

  return (
    <section className="mx-auto max-w-sm">
      <h1 className="text-balance text-2xl tracking-tight text-ink">
        Admin access
      </h1>

      {authed ? (
        <div className="mt-6">
          <p className="font-sans text-sm text-ink-muted">
            You&apos;re in admin mode. Uploads and deletes are unlocked.
          </p>
          <Button
            variant="danger"
            className="mt-5"
            onClick={() => {
              clearSecret();
              router.replace("/");
            }}
          >
            Switch to guest mode
          </Button>
        </div>
      ) : (
        <AuthForm
          onSubmit={(secret) => {
            setSecret(secret);
            router.replace("/");
          }}
        />
      )}

      <Link
        href="/"
        className="mt-8 inline-flex items-center gap-1 font-sans text-sm text-ink-muted transition-colors hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
      >
        &larr; Back to library
      </Link>
    </section>
  );
}

function AuthForm({ onSubmit }: { onSubmit: (secret: string) => void }) {
  const [value, setValue] = useState("");
  const trimmed = value.trim();

  return (
    <form
      className="mt-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (trimmed) onSubmit(trimmed);
      }}
    >
      <label
        htmlFor="admin-secret"
        className="font-sans text-sm text-ink-muted"
      >
        Enter the admin secret to unlock writes.
      </label>
      <Input
        id="admin-secret"
        type="password"
        autoComplete="off"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Admin secret"
        className="mt-3 w-full"
      />
      <Button type="submit" disabled={!trimmed} className="mt-4 w-full">
        Authenticate
      </Button>
    </form>
  );
}
