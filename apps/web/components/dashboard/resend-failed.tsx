"use client";

import { useEffect, useRef, useState } from "react";

import { toApiError, type ResendFailedResult, type ResendFailedScope } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { buttonClass } from "./ui";

/** "Resend failed emails": a dry run fills a confirmation dialog with the
 *  server's own count, and confirming queues them.
 *
 *  Queued, not sent: the API marks each row scheduled and its once-a-minute
 *  sweep sends them through the same sender as every other email, so the
 *  provider's daily limit still applies. That is why the success message says
 *  "queued" and never "sent" — nothing has been sent when it appears.
 */
export function ResendFailedButton({
  slug,
  scope,
  onQueued,
  className,
}: {
  slug: string;
  scope: ResendFailedScope;
  /** Called after a real queue, with the server's answer. */
  onQueued: (result: ResendFailedResult) => void;
  className?: string;
}) {
  const api = useCertForge();
  const [preview, setPreview] = useState<ResendFailedResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setError(null);
    setChecking(true);
    try {
      setPreview(await api.resendFailed(slug, scope, true));
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setChecking(false);
    }
  }

  async function confirm() {
    const result = await api.resendFailed(slug, scope, false);
    setPreview(null);
    onQueued(result);
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        disabled={checking}
        className={className ?? buttonClass("secondary", "sm")}
      >
        {checking ? "Checking…" : "Resend failed emails"}
      </button>
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
      <ResendFailedDialog preview={preview} onCancel={() => setPreview(null)} onConfirm={confirm} />
    </>
  );
}

/** The sentence a notice shows after a queue. Shared so both callers say the
 *  same thing about the same answer. */
export function describeQueued(result: ResendFailedResult): string {
  if (result.queued === 0) return "No failed emails could be resent.";
  const n = result.queued === 1 ? "1 email" : `${result.queued} emails`;
  const when = result.paused_until
    ? ` Sending is paused by the email provider's daily limit until ${formatWhen(result.paused_until)}; they go out after that.`
    : " They go out within a minute or so.";
  const more = result.capped ? ` More remain — run it again to queue the rest.` : "";
  return `${n} queued to resend.${when}${more}`;
}

function formatWhen(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function skippedLines(result: ResendFailedResult): string[] {
  const { attempt_limit, revoked, no_email, test } = result.skipped;
  const lines: string[] = [];
  if (attempt_limit) lines.push(`${attempt_limit} already emailed ${result.attempts_max} times`);
  if (revoked) lines.push(`${revoked} revoked`);
  if (no_email) lines.push(`${no_email} with no email address`);
  if (test) lines.push(`${test} test credential${test === 1 ? "" : "s"}`);
  return lines;
}

/** A native modal, like the revoke dialog: focus trap, Escape and backdrop. */
function ResendFailedDialog({
  preview,
  onCancel,
  onConfirm,
}: {
  preview: ResendFailedResult | null;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (preview && !node.open) node.showModal();
    if (!preview && node.open) node.close();
    if (preview) setError(null);
  }, [preview]);

  const skipped = preview ? skippedLines(preview) : [];
  const count = preview ? Math.min(preview.eligible, preview.max) : 0;

  return (
    <dialog
      ref={dialog}
      onClose={onCancel}
      aria-labelledby="resend-failed-title"
      className="m-auto max-w-md rounded-xl border border-hair bg-surface p-6 text-ink shadow-[var(--cf-shadow-card)] backdrop:bg-ink/40"
    >
      {preview ? (
        <>
          <h2 id="resend-failed-title" className="font-display text-lg font-semibold">
            {count === 0 ? "Nothing to resend" : `Resend ${count} failed email${count === 1 ? "" : "s"}?`}
          </h2>
          {count > 0 ? (
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Each recipient is emailed their credential again. Every resend uses one of that
              credential’s {preview.attempts_max} send attempts.
              {preview.capped ? ` Only the ${preview.max} oldest are queued this time.` : ""}
            </p>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-muted">
              None of the failed emails here can be sent again.
            </p>
          )}
          {skipped.length > 0 ? (
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Left out: {skipped.join(", ")}.
            </p>
          ) : null}
          {preview.paused_until ? (
            <p className="mt-2 text-sm leading-relaxed text-warn-ink">
              The email provider’s daily send limit is reached until{" "}
              {formatWhen(preview.paused_until)}. These will be queued now and sent after that.
            </p>
          ) : null}
          {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onCancel} className={buttonClass("secondary", "sm")}>
              {count === 0 ? "Close" : "Cancel"}
            </button>
            {count > 0 ? (
              <button
                type="button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await onConfirm();
                  } catch (err) {
                    setError(toApiError(err).message);
                  } finally {
                    setBusy(false);
                  }
                }}
                className={buttonClass("primary", "sm")}
              >
                {busy ? "Queuing…" : `Resend ${count}`}
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </dialog>
  );
}
