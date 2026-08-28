"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { toApiError, type BatchDelivery, type BatchStatus, type TemplateSummary } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { Card, EmptyNote, ErrorNote, Skeleton } from "./ui";

const TERMINAL_STATUSES = new Set(["completed", "completed_with_errors", "failed"]);
const POLL_INTERVAL_MS = 2000;

export function BulkIssueCard({ slug, onIssued }: { slug: string; onIssued: () => void }) {
  const api = useCertForge();

  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState("");

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchStatus | null>(null);

  const onIssuedRef = useRef(onIssued);
  useEffect(() => {
    onIssuedRef.current = onIssued;
  }, [onIssued]);

  // Bulk issuance needs a template id, so the org's own templates and the
  // global ones are merged. Org templates require a role the viewer may not
  // have; a failure there must not hide the global list.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    Promise.allSettled([
      api.listGlobalTemplates(controller.signal),
      api.listOrgTemplates(slug, controller.signal),
    ]).then((results) => {
      if (cancelled) return;
      const available = results.flatMap((result) =>
        result.status === "fulfilled" ? result.value : [],
      );
      if (results.every((result) => result.status === "rejected")) {
        const reason = results[0].status === "rejected" ? results[0].reason : null;
        setTemplatesError(toApiError(reason).message);
        setTemplates([]);
        return;
      }
      setTemplates(available);
      setTemplateId((current) => current || available[0]?.id || "");
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, slug]);

  // Batch processing is asynchronous server-side; poll until it settles rather
  // than claiming a result the worker has not produced.
  useEffect(() => {
    if (!batch || TERMINAL_STATUSES.has(batch.status)) return;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .getBatch(slug, batch.id, controller.signal)
        .then((next) => {
          setBatch(next);
          if (TERMINAL_STATUSES.has(next.status)) onIssuedRef.current();
        })
        .catch(() => {
          // Leave the last known status on screen; the next render will retry.
        });
    }, POLL_INTERVAL_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, slug, batch]);

  const upload = useCallback(async () => {
    if (!file || !templateId) return;
    setUploading(true);
    setUploadError(null);
    setBatch(null);
    try {
      const result = await api.bulkIssueFromCsv(slug, { templateId, file });
      setBatch({
        id: result.batch_id,
        status: result.status,
        total: result.total,
        succeeded: 0,
        failed: 0,
        // Zeroes are honest here — the worker has not run yet. DeliveryLine is
        // only rendered once the batch settles, so these are never displayed.
        delivery: { delivered: 0, failed: 0, not_requested: 0 },
        error_report: null,
        created_at: new Date().toISOString(),
        completed_at: null,
      });
    } catch (err) {
      setUploadError(toApiError(err).message);
    } finally {
      setUploading(false);
    }
  }, [api, file, slug, templateId]);

  const noTemplates = templates !== null && templates.length === 0;

  return (
    <Card
      title="Bulk issue via CSV"
      description="One credential per row. The CSV must have name and title columns; email is optional."
    >
      {templates === null ? (
        <Skeleton rows={1} />
      ) : templatesError ? (
        <ErrorNote>Could not load templates: {templatesError}</ErrorNote>
      ) : noTemplates ? (
        <EmptyNote>
          No templates are available to this organization yet, so credentials cannot be issued.
        </EmptyNote>
      ) : (
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-zinc-300">Template</span>
          <select
            value={templateId}
            onChange={(event) => setTemplateId(event.target.value)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-100 focus:border-indigo-500/60 focus:outline-none"
          >
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
                {template.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="group relative mt-6 overflow-hidden rounded-xl border-2 border-dashed border-zinc-800 p-12 text-center transition-colors hover:border-indigo-500/50">
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
        />
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-zinc-800/50 transition-colors group-hover:bg-indigo-500/10">
          <svg
            className="h-8 w-8 text-zinc-400 transition-colors group-hover:text-indigo-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>
        <p className="mb-1 font-medium text-zinc-300">
          {file ? file.name : "Click or drop a CSV file here"}
        </p>
        <p className="text-sm text-zinc-500">Nothing is uploaded until you start the issuance.</p>
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={upload}
          disabled={!file || !templateId || uploading}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-500"
        >
          {uploading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-400 border-t-white" />
              Uploading…
            </>
          ) : (
            "Start issuance"
          )}
        </button>
      </div>

      {uploadError ? (
        <div className="mt-6">
          <ErrorNote>{uploadError}</ErrorNote>
        </div>
      ) : null}

      {batch ? <BatchResult batch={batch} /> : null}
    </Card>
  );
}

function BatchResult({ batch }: { batch: BatchStatus }) {
  const settled = TERMINAL_STATUSES.has(batch.status);
  const tone = !settled
    ? "border-indigo-500/20 bg-indigo-500/10 text-indigo-300"
    : batch.status === "completed"
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
      : "border-amber-500/20 bg-amber-500/10 text-amber-300";

  return (
    <div className={`mt-6 rounded-xl border p-4 ${tone}`}>
      <h4 className="font-medium">
        {settled ? `Batch ${batch.status.replace(/_/g, " ")}` : "Batch queued"}
      </h4>
      <p className="mt-1 text-sm opacity-90">
        {settled
          ? `${batch.succeeded} of ${batch.total} issued${batch.failed > 0 ? `, ${batch.failed} failed` : ""}.`
          : `${batch.total} rows accepted. Waiting on the issuance worker…`}
      </p>
      {settled ? <DeliveryLine delivery={batch.delivery} /> : null}
      <p className="mt-2 font-mono text-xs opacity-70">Batch ID: {batch.id}</p>
    </div>
  );
}

/** Issued and delivered are different numbers, and the line above only knows
 *  the first. Saying "30 issued" while 30 emails failed is how a batch that
 *  reached nobody read as a clean success. */
function DeliveryLine({ delivery }: { delivery: BatchDelivery | undefined }) {
  // An older API, or a batch that predates delivery tracking, sends nothing
  // here. Claiming "0 delivered" for those would be inventing a fact.
  if (!delivery) return null;

  const { delivered, failed, not_requested: notRequested } = delivery;

  if (failed === 0 && delivered === 0 && notRequested > 0) {
    return (
      <p className="mt-1 text-sm opacity-75">
        No emails sent — {notRequested === 1 ? "the row had" : "the rows had"} no address, or
        delivery was not requested.
      </p>
    );
  }

  const parts = [`${delivered} delivered`];
  if (failed > 0) parts.push(`${failed} failed`);
  if (notRequested > 0) parts.push(`${notRequested} not sent`);

  return (
    <p className={`mt-1 text-sm ${failed > 0 ? "font-medium" : "opacity-75"}`}>
      {parts.join(", ")}.
      {failed > 0 ? " Failed sends are retried automatically." : ""}
    </p>
  );
}
