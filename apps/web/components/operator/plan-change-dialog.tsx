"use client";

import { useEffect, useId, useRef, useState } from "react";

import { toApiError, type OperatorTierResult } from "@/lib/api";
import { MIN_REASON_LENGTH, formatLimit, isReasonValid, type PlanChangeDiff } from "@/lib/operator";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote, buttonClass, inputClass } from "@/components/dashboard/ui";
import { Spinner } from "./bits";

/**
 * Confirms a plan change before it is sent: the plan and the enforced limit
 * before and after, and — because `change_tier()` always clears it — the
 * override that will be removed, by value. The reason is asked for here, at
 * the moment it is being spent, rather than in a field shared with the
 * override form.
 *
 * A native modal `<dialog>`: focus is trapped inside it and Esc closes it
 * without any code here. Esc is ignored while saving, so the request's
 * outcome is never hidden behind a closed dialog.
 */
export function PlanChangeDialog({
  slug,
  orgName,
  targetTier,
  diff,
  onCancel,
  onDone,
}: {
  slug: string;
  orgName: string;
  /** null keeps the dialog closed. */
  targetTier: string | null;
  diff: PlanChangeDiff | null;
  onCancel: () => void;
  onDone: (result: OperatorTierResult) => void;
}) {
  const api = useCertForge();
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const reasonId = useId();
  const hintId = useId();
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = targetTier !== null && diff !== null;

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) {
      setReason("");
      setError(null);
      node.showModal();
    }
    if (!open && node.open) node.close();
  }, [open]);

  async function confirm() {
    if (!targetTier || !isReasonValid(reason) || saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.setOrgTier(slug, { tier: targetTier, reason: reason.trim() });
      onDone(result);
    } catch (err) {
      // Stays open: the operator's reason and the diff are still on screen.
      setError(toApiError(err).message);
    } finally {
      setSaving(false);
    }
  }

  const reasonOk = isReasonValid(reason);

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        if (saving) event.preventDefault();
      }}
      onClose={() => {
        if (open) onCancel();
      }}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-hair bg-surface p-6 text-ink shadow-[var(--cf-shadow-card)] backdrop:bg-ink/40"
    >
      {open && diff ? (
        <form
          method="dialog"
          onSubmit={(event) => {
            event.preventDefault();
            void confirm();
          }}
        >
          <h2 id={titleId} className="font-display text-lg font-semibold">
            Change {orgName}&apos;s plan?
          </h2>

          <p className="mt-4 rounded-lg border border-hair bg-well px-4 py-3 font-mono text-sm">
            {diff.before} <span aria-hidden>→</span>
            <span className="sr-only">to</span> {diff.after}
          </p>
          <p className="mt-2 text-sm text-muted">
            Enforced limit {formatLimit(diff.enforcedBefore)} → {formatLimit(diff.enforcedAfter)} a month. No
            payment is taken.
          </p>

          {diff.removesOverride ? (
            <p role="alert" className="mt-3 rounded-lg border border-warn-line bg-warn-wash px-4 py-3 text-sm text-warn-ink">
              This removes the credential override of{" "}
              <strong className="font-semibold">{formatLimit(diff.removesOverride.limit)}</strong> a month. The org
              will follow the new plan&apos;s limit instead.
            </p>
          ) : null}

          <label htmlFor={reasonId} className="mt-5 mb-1.5 block text-sm font-medium text-ink">
            Reason
          </label>
          <textarea
            id={reasonId}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            maxLength={1000}
            required
            autoFocus
            disabled={saving}
            aria-describedby={hintId}
            placeholder="Why, for whoever asks in six months."
            className={`${inputClass} disabled:bg-well disabled:text-muted`}
          />
          <span id={hintId} className="mt-1 block text-xs text-faint">
            At least {MIN_REASON_LENGTH} characters. Saved in the change log with your user id.
          </span>

          {error ? (
            <div className="mt-4">
              <ErrorNote>{error}</ErrorNote>
            </div>
          ) : null}

          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onCancel} disabled={saving} className={buttonClass("secondary", "sm")}>
              Cancel
            </button>
            <button type="submit" disabled={saving || !reasonOk} className={`${buttonClass("primary", "sm")} gap-2`}>
              {saving ? (
                <>
                  <Spinner /> Saving…
                </>
              ) : (
                "Change plan"
              )}
            </button>
          </div>
        </form>
      ) : null}
    </dialog>
  );
}
