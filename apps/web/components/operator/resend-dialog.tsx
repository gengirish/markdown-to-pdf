"use client";

import { useEffect, useId, useRef, useState } from "react";

import { toApiError, type OperatorDelivery, type OperatorResendResult } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/operator";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote, Mono, buttonClass } from "@/components/dashboard/ui";
import { Spinner } from "./bits";

/** The API's ceiling (`MAX_DELIVERY_ATTEMPTS`), shown so the operator knows
 *  how many tries are left. The API enforces it. */
const MAX_ATTEMPTS = 3;

/**
 * Confirms an operator resend. One idempotency key per opening of the
 * dialog: a double-click on Confirm sends the same key twice, and the API
 * answers the second from the first instead of mailing the recipient again.
 * The button is also disabled while the request is in flight; the key is
 * what makes that safe rather than hopeful.
 */
export function ResendDialog({
  delivery,
  onCancel,
  onDone,
}: {
  /** null keeps the dialog closed. */
  delivery: OperatorDelivery | null;
  onCancel: () => void;
  onDone: (result: OperatorResendResult) => void;
}) {
  const api = useCertForge();
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const key = useRef<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (delivery && !node.open) {
      key.current = newIdempotencyKey();
      setError(null);
      node.showModal();
    }
    if (!delivery && node.open) node.close();
  }, [delivery]);

  async function confirm() {
    if (!delivery || !key.current) return;
    setSending(true);
    setError(null);
    try {
      onDone(await api.resendOperatorDelivery(delivery.id, key.current));
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        if (sending) event.preventDefault();
      }}
      onClose={() => {
        if (delivery) onCancel();
      }}
      className="m-auto w-[min(30rem,calc(100vw-2rem))] rounded-xl border border-hair bg-surface p-6 text-ink shadow-[var(--cf-shadow-card)] backdrop:bg-ink/40"
    >
      {delivery ? (
        <>
          <h2 id={titleId} className="font-display text-lg font-semibold">
            Resend this email?
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {delivery.recipient_name} ({delivery.recipient_email}) will be emailed “{delivery.title}” again, on
            behalf of {delivery.org_name}. This is recorded under your user id.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-hair bg-well px-4 py-3 text-sm">
            <div>
              <dt className="text-faint">Credential</dt>
              <dd>
                <Mono>{delivery.id}</Mono>
              </dd>
            </div>
            <div>
              <dt className="text-faint">Attempts</dt>
              <dd className="font-mono">
                {delivery.delivery_attempts} of {MAX_ATTEMPTS}
              </dd>
            </div>
            {delivery.delivery_error ? (
              <div className="col-span-2">
                <dt className="text-faint">Last error</dt>
                <dd className="break-words text-danger">{delivery.delivery_error}</dd>
              </div>
            ) : null}
          </dl>
          {error ? (
            <div className="mt-4">
              <ErrorNote>{error}</ErrorNote>
            </div>
          ) : null}
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onCancel} disabled={sending} className={buttonClass("secondary", "sm")}>
              Cancel
            </button>
            <button
              type="button"
              autoFocus
              onClick={() => void confirm()}
              disabled={sending}
              className={`${buttonClass("primary", "sm")} gap-2`}
            >
              {sending ? (
                <>
                  <Spinner /> Sending…
                </>
              ) : (
                "Resend email"
              )}
            </button>
          </div>
        </>
      ) : null}
    </dialog>
  );
}
