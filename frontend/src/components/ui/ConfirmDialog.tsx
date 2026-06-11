"use client";

import { useEffect, useRef } from "react";
import { Check } from "lucide-react";
import { Button } from "./Button";

// Generic confirm modal. Presentational: the caller owns the mechanism (the
// mutation, cache update, navigation) and feeds `busy`/`error`/`success` back
// in. Native <dialog> driven from `open`; Escape and backdrop click resolve to
// `onCancel`. While `busy` or after `success` the dialog is locked (the caller
// is mid-request or about to navigate away).
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  busyLabel,
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  error = null,
  success = false,
  successLabel = "Done",
  successHint,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body?: React.ReactNode;
  confirmLabel?: string;
  busyLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  error?: string | null;
  success?: boolean;
  successLabel?: string;
  successHint?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const locked = busy || success;

  // Drive the native modal from `open`; the <dialog> `onClose` syncs Esc/native
  // closes back so state never desyncs (the BookUploadDialog pattern).
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    else if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      // Esc fires `cancel` then `close`; block it while locked so the dialog
      // can't be dismissed mid-request or during the success handoff.
      onCancel={(e) => {
        if (locked) e.preventDefault();
      }}
      onClose={onCancel}
      // Backdrop click (target is the <dialog> itself, never the inner box)
      // cancels, but not while locked.
      onClick={(e) => {
        if (!locked && e.target === ref.current) onCancel();
      }}
      className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-xl border border-rule bg-paper text-ink opacity-0 backdrop:bg-ink/20 backdrop:opacity-0 transition-discrete duration-150 transition-[opacity,overlay,display] open:opacity-100 open:backdrop:opacity-100 starting:open:opacity-0 starting:open:backdrop:opacity-0"
    >
      <div className="p-6">
        {success ? (
          <div className="flex flex-col items-center gap-2.5 py-3 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-status-ready/15 text-status-ready">
              <Check aria-hidden className="h-5 w-5" strokeWidth={2.5} />
            </span>
            <p className="text-base font-medium text-ink">{successLabel}</p>
            {successHint && (
              <p className="font-sans text-sm text-ink-muted">{successHint}</p>
            )}
          </div>
        ) : (
          <>
            <h2 className="text-lg font-medium tracking-tight text-ink">
              {title}
            </h2>
            {body && (
              <div className="mt-2 font-sans text-sm text-ink-muted">{body}</div>
            )}
            {error && (
              <p
                role="alert"
                className="mt-3 flex items-center gap-2 font-sans text-sm text-status-failed"
              >
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-status-failed" />
                {error}
              </p>
            )}
            <div className="mt-6 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={onCancel}
                disabled={busy}
                className="cursor-pointer rounded-lg border border-rule bg-paper px-4 py-2.5 font-sans text-sm font-medium text-ink transition-colors hover:bg-paper-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-1 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:opacity-40"
              >
                {cancelLabel}
              </button>
              <Button
                variant={destructive ? "danger" : "primary"}
                onClick={onConfirm}
                disabled={busy}
              >
                {busy ? (busyLabel ?? confirmLabel) : confirmLabel}
              </Button>
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}
