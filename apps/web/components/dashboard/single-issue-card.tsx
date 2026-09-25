"use client";

import { useCallback, useId, useState } from "react";

import { toApiError, type DeliveryState, type IssuedCredential } from "@/lib/api";
import { LOOSE_EMAIL } from "@/lib/csv";
import { useCertForge } from "@/lib/use-api";
import { useIssuableTemplates } from "@/lib/use-templates";
import { Card, ErrorNote, buttonClass, inputClass } from "./ui";


export function SingleIssueCard({ slug, onIssued }: { slug: string; onIssued: () => void }) {
  const api = useCertForge();

  const templates = useIssuableTemplates(slug);
  const [templateId, setTemplateId] = useState("");

  const [recipientName, setRecipientName] = useState("");
  const [title, setTitle] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [sendEmail, setSendEmail] = useState(false);
  // Once someone has touched the box, their choice stands: typing a valid
  // address ticks it only for a person who has not already said no.
  const [sendTouched, setSendTouched] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<IssuedCredential | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const reasonId = useId();

  // The box means nothing without an address to send to, so it is disabled
  // until there is one and ignored if the address is cleared after ticking it.
  const hasEmail = recipientEmail.trim() !== "";
  const willSend = sendEmail && hasEmail;

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
        sendEmail: willSend,
      });
      setResult(issued);
      setRecipientName("");
      setTitle("");
      setRecipientEmail("");
      setSendEmail(false);
      setSendTouched(false);
      onIssued();
    } catch (err) {
      setSubmitError(toApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  }, [api, slug, recipientName, title, recipientEmail, templateId, willSend, onIssued]);

  const missing = [!recipientName && "a recipient name", !title && "a title"].filter(Boolean);
  const disabled = missing.length > 0 || submitting;
  const disabledReason = missing.length > 0 ? `Add ${missing.join(" and ")} to issue.` : null;

  function changeEmail(value: string) {
    setRecipientEmail(value);
    // The cohort check's rule: loose, because this only decides whether to
    // pre-tick the box. The server is what rejects a bad address.
    if (!sendTouched) setSendEmail(LOOSE_EMAIL.test(value.trim()));
  }

  // The template this credential will actually render with: the one chosen,
  // or what the API resolves with none sent.
  const effectiveTemplate =
    templates.status === "ready"
      ? templateId
        ? templates.templates.find((tpl) => tpl.id === templateId)
        : templates.defaultTemplate
      : undefined;
  const canPreview =
    templates.status === "ready" &&
    effectiveTemplate !== undefined &&
    templates.ownIds.has(effectiveTemplate.id);

  /** Renders the design with sample data, as the Templates tab does. The tab
   *  is opened first, inside the click, so it is not blocked as a popup. */
  async function preview() {
    if (!effectiveTemplate) return;
    const tab = window.open("", "_blank");
    if (tab) tab.opener = null;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const detail = await api.getOrgTemplate(slug, effectiveTemplate.id);
      const blob = await api.previewTemplate(
        slug,
        detail.config
          ? { config: detail.config, backgroundAssetId: detail.background_asset_id }
          : { htmlSource: detail.html_source },
      );
      const url = URL.createObjectURL(blob);
      if (tab) {
        tab.location.href = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = "template-preview.pdf";
        link.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      tab?.close();
      setPreviewError(toApiError(err).message);
    } finally {
      setPreviewing(false);
    }
  }

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
            className={inputClass}
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">Title</span>
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={inputClass}
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">
            Recipient email (optional)
          </span>
          <input
            type="email"
            value={recipientEmail}
            onChange={(event) => changeEmail(event.target.value)}
            className={inputClass}
          />
        </label>

        <div>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">Template</span>
            <select
              value={templateId}
              onChange={(event) => setTemplateId(event.target.value)}
              disabled={templates.status !== "ready"}
              className={inputClass}
            >
              {templates.status === "loading" ? (
                <option value="">Loading templates…</option>
              ) : templates.status === "error" ? (
                <option value="">Organization default</option>
              ) : (
                <>
                  <option value="">
                    {templates.defaultTemplate
                      ? `Organization default — ${templates.defaultTemplate.name}`
                      : "Organization default"}
                  </option>
                  {templates.templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                      {template.is_default ? " (default)" : ""}
                    </option>
                  ))}
                </>
              )}
            </select>
          </label>
          {templates.status === "error" ? (
            // Not blocking: with no template_id the server still resolves the
            // default, so the form can issue while the list is unavailable.
            <p className="mt-2 text-xs text-danger">
              Could not load templates: {templates.message}{" "}
              <button
                type="button"
                onClick={templates.retry}
                className="font-medium underline underline-offset-2"
              >
                Retry
              </button>
            </p>
          ) : effectiveTemplate ? (
            <div className="mt-2">
              {canPreview ? (
                <button
                  type="button"
                  onClick={preview}
                  disabled={previewing}
                  className={buttonClass("secondary", "sm")}
                >
                  {previewing ? "Rendering…" : "Preview design"}
                </button>
              ) : (
                <p className="text-xs text-muted">
                  A built-in design. Preview is available for your own designs.
                </p>
              )}
            </div>
          ) : null}
          {previewError ? <p className="mt-2 text-xs text-danger">{previewError}</p> : null}
        </div>
      </div>

      <label
        className={`mt-4 flex items-center gap-2 text-sm ${hasEmail ? "text-ink" : "text-faint"}`}
      >
        <input
          type="checkbox"
          checked={willSend}
          disabled={!hasEmail}
          onChange={(event) => {
            setSendTouched(true);
            setSendEmail(event.target.checked);
          }}
          className="h-4 w-4 rounded border-hair-strong bg-surface text-accent focus:ring-accent"
        />
        Send email to recipient
        {hasEmail ? null : <span className="text-xs">— add an email address first</span>}
      </label>

      <div className="mt-6 flex items-center justify-end gap-4">
        {disabledReason && !submitting ? (
          <p id={reasonId} className="text-xs text-muted">
            {disabledReason}
          </p>
        ) : null}
        <button
          type="button"
          onClick={issue}
          disabled={disabled}
          aria-describedby={disabledReason ? reasonId : undefined}
          title={disabledReason ?? undefined}
          className="flex items-center gap-2 rounded-lg bg-accent px-6 py-3 font-medium text-ground transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {submitting ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-hair-strong border-t-ground" />
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
