"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";

type ConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  organizationName: string;
  confirmLabel?: string;
  onConfirm: () => void | Promise<void>;
};

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  organizationName,
  confirmLabel = "Confirm destructive action",
  onConfirm,
}: ConfirmDialogProps) {
  const [typedName, setTypedName] = useState("");
  const [sure, setSure] = useState(false);
  const [delayElapsed, setDelayElapsed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open || !sure) {
      setDelayElapsed(false);
      return;
    }
    const timeout = window.setTimeout(() => setDelayElapsed(true), 3000);
    return () => window.clearTimeout(timeout);
  }, [open, sure]);

  useEffect(() => {
    if (!open) {
      setTypedName("");
      setSure(false);
      setSubmitting(false);
    }
  }, [open]);

  if (!open) return null;

  const canConfirm = typedName === organizationName && sure && delayElapsed && !submitting;

  async function handleConfirm() {
    if (!canConfirm) return;
    setSubmitting(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="w-full max-w-lg rounded-t-lg bg-surface p-5 shadow-xl sm:rounded-lg sm:p-6"
      >
        <h2 id="confirm-dialog-title" className="text-lg font-semibold text-charcoal">{title}</h2>
        <p id="confirm-dialog-description" className="mt-2 text-sm leading-6 text-text-secondary">{description}</p>
        <label className="mt-5 block text-sm font-medium text-charcoal" htmlFor="confirm-org-name">
          Type <span className="font-semibold">{organizationName}</span> to continue
        </label>
        <input
          id="confirm-org-name"
          autoComplete="off"
          value={typedName}
          onChange={event => setTypedName(event.target.value)}
          className="mt-2 min-h-11 w-full rounded-md border border-border bg-surface px-3 text-base text-charcoal outline-none focus-visible:ring-2 focus-visible:ring-red-600"
        />
        <label className="mt-4 flex min-h-11 cursor-pointer items-center gap-3 text-sm text-charcoal">
          <input
            type="checkbox"
            checked={sure}
            onChange={event => setSure(event.target.checked)}
            className="size-5 accent-red-700"
          />
          Are you sure? This action may not be reversible.
        </label>
        {sure && !delayElapsed ? (
          <p role="status" className="text-sm text-text-secondary">Destructive action unlocks in 3 seconds.</p>
        ) : null}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" className="min-h-11" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            className="min-h-11 bg-red-700 text-white hover:bg-red-800 focus-visible:ring-red-700"
            disabled={!canConfirm}
            onClick={handleConfirm}
          >
            {submitting ? "Working..." : confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}