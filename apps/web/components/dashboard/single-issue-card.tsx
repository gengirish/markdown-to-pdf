"use client";

import { useCallback, useEffect, useState } from "react";

import {
  toApiError,
  type DeliveryState,
  type IssuedCredential,
  type TemplateSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { Card, ErrorNote } from "./ui";

export function SingleIssueCard({ slug, onIssued }: { slug: string; onIssued: () => void }) {
  const api = useCertForge();

  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [templateId, setTemplateId] = useState("");

  const [recipientName, setRecipientName] = useState("");
  const [title, setTitle] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [sendEmail, setSendEmail] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<IssuedCredential | null>(null);

  // Templates are optional here: the server can resolve a global default with
  // no template_id sent, so an empty or failed load must not block the form.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    Promise.allSettled([
      api.listGlobalTemplates(controller.signal),
      api.listOrgTemplates(slug, controller.signal),
    ]).then((results) => {
      if (cancelled) return;
      const available = results.flatMap((res) => (res.status === "fulfilled" ? res.value : []));
      setTemplates(available);
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, slug]);

  const issue = useCallback(async () => {
    if (!recipientName || !title) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const issued = await api.issueCredential(slug, {
        recipientName,
        title,
        recipientEmail: recipientEmail || undefined,
        templateId: templateId || undefined,
        sendEmail,
      });
      setResult(issued);
      setRecipientName("");
      setTitle("");
      setRecipientEmail("");
      onIssued();
    } catch (err) {
      setSubmitError(toApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  }, [api, slug, recipientName, title, recipientEmail, templateId, sendEmail, onIssued]);

  const disabled = !recipientName || !title || submitting;

  return (
    <Card
      title="Issue a single credential"
      description="Issue one credential immediately, without a CSV."
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">Recipient name</span>
          <input
            type="text"
            value={recipientName}
            onChange={(event) => setRecipientName(event.target.value)}
            className="w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink focus:border-accent focus:outline-none"
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">Title</span>
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink focus:border-accent focus:outline-none"
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">
            Recipient email (optional)
          </span>
          <input
            type="email"
            value={recipientEmail}
            onChange={(event) => setRecipientEmail(event.target.value)}
            className="w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink focus:border-accent focus:outline-none"
          />
        </label>

        {templates && templates.length > 0 ? (
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">Template</span>
            <select
              value={templateId}
              onChange={(event) => setTemplateId(event.target.value)}
              className="w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink focus:border-accent focus:outline-none"
            >
              <option value="">Auto (org default)</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                  {template.is_default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <label className="mt-4 flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={sendEmail}
          onChange={(event) => setSendEmail(event.target.checked)}
          className="h-4 w-4 rounded border-hair-strong bg-surface text-accent focus:ring-accent"
        />
        Send email to recipient
      </label>

      <div className="mt-6 flex justify-end">
        <button
          onClick={issue}
          disabled={disabled}
          className="flex items-center gap-2 rounded-lg bg-accent px-6 py-3 font-medium text-ground transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {submitting ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-hair-strong border-t-white" />
              Issuing…
            </>
          ) : (
            "Issue credential"
          )}
        </button>
      </div>

      {submitError ? (
        <div className="mt-6">
          <ErrorNote>{submitError}</ErrorNote>
        </div>
      ) : null}

      {result ? <IssueResult result={result} /> : null}
    </Card>
  );
}

function IssueResult({ result }: { result: IssuedCredential }) {
  return (
    <div className="mt-6 rounded-xl border border-accent-line bg-accent-wash p-4 text-accent">
      <h4 className="font-medium">Issued</h4>
      <p className="mt-1 text-sm opacity-90">
        {result.recipient_name} — {result.title}
      </p>
      <DeliveryNote delivery={result.delivery} />
      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        <a
          href={result.verify_url}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-accent"
        >
          Verify page
        </a>
        <a
          href={result.pdf_url}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-accent"
        >
          Download PDF
        </a>
        <a
          href={result.badge_url}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-accent"
        >
          Badge JSON
        </a>
      </div>
    </div>
  );
}

/** Whether the recipient was actually emailed, said plainly next to the
 *  checkbox that asked for it. Before this, a rejected send and a send that was
 *  never requested both looked exactly like success. */
function DeliveryNote({ delivery }: { delivery: DeliveryState | undefined }) {
  if (!delivery) return null;

  if (delivery.status === "sent") {
    return <p className="mt-2 text-sm opacity-90">Email sent to the recipient.</p>;
  }

  if (delivery.status === "failed") {
    return (
      <p className="mt-2 rounded-lg border border-warn-line bg-warn-wash px-3 py-2 text-sm text-warn-ink">
        The credential was issued, but the email did not send
        {delivery.error ? `: ${delivery.error}` : "."}
        {delivery.may_retry ? " It will be retried automatically." : ""}
      </p>
    );
  }

  if (delivery.status === "not_requested") {
    return <p className="mt-2 text-sm opacity-75">No email sent — share the link instead.</p>;
  }

  return null;
}
