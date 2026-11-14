"use client";

import { useEffect, useRef, useState } from "react";

import {
  toApiError,
  type ApiError,
  type DeliveryStatus,
  type OperatorDelivery,
  type OperatorDeliveryFilter,
  type OperatorDeliveryPage,
} from "@/lib/api";
import {
  DATE_RANGES,
  formatAbsolute,
  nextSort,
  rangeBounds,
  type DateRange,
  type DeliverySortValue,
  type OperatorParams,
} from "@/lib/operator";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote, Mono, Skeleton, StatusTag, buttonClass, inputClass } from "@/components/dashboard/ui";
import { CloseIcon, QualityBadge, SortHeader, Spinner } from "./bits";
import { OrgPicker } from "./org-picker";
import { ResendDialog } from "./resend-dialog";

const PAGE_SIZE = 50;

const FILTERS: { value: OperatorDeliveryFilter; label: string }[] = [
  { value: "attempted", label: "All emails" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
  { value: "deferred", label: "Scheduled (daily limit)" },
  { value: "pending", label: "Pending" },
  { value: "unknown", label: "Unknown (pre-tracking)" },
  { value: "not_requested", label: "Not emailed" },
  { value: "all", label: "Every credential" },
];

const RANGE_LABEL: Record<DateRange, string> = {
  all: "Any time",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  custom: "Custom range…",
};

/** Rows an operator would expect to resend; only these explain a refusal.
 *  A sent row has no button and needs no reason. */
const STUCK: ReadonlySet<DeliveryStatus> = new Set<DeliveryStatus>([
  "failed",
  "pending",
  "unknown",
  // Never resendable; its refusal says when it sends on its own.
  "deferred",
]);

const TONE: Record<DeliveryStatus, "ok" | "warn" | "neutral" | "bad"> = {
  sent: "ok",
  failed: "bad",
  deferred: "warn",
  pending: "warn",
  unknown: "neutral",
  not_requested: "neutral",
};

const LABEL: Record<DeliveryStatus, string> = {
  sent: "Sent",
  failed: "Failed",
  deferred: "Scheduled",
  pending: "Pending",
  unknown: "Unknown",
  not_requested: "Not emailed",
};

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Which org emailed which recipient, and what became of each send. The API
 * is the operator-only `GET /api/v1/operator/deliveries`; resend and export
 * are its siblings.
 *
 * Every filter, the sort and the page are the page's state, kept in the URL.
 * The org filter is always visible as a removable chip: it used to be
 * inherited invisibly from the Plans tab, which read as "0 total" and broken.
 *
 * Paged, not "load more": changing page keeps the current rows on screen
 * (dimmed) until the next ones arrive, so the table never collapses and the
 * scroll position holds.
 */
export function DeliveriesPanel({
  params,
  onParams,
  onToast,
}: {
  params: OperatorParams;
  onParams: (patch: Partial<OperatorParams>) => void;
  onToast: (message: string) => void;
}) {
  const api = useCertForge();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  // The chip names the org; a slug from a pasted URL is looked up once.
  const [orgName, setOrgName] = useState<{ slug: string; name: string } | null>(null);
  const [data, setData] = useState<OperatorDeliveryPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [resending, setResending] = useState<OperatorDelivery | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const { org, status: filter, range, from, to, mailSort, mailDir, page } = params;

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!org || orgName?.slug === org) return;
    const controller = new AbortController();
    api
      .listOperatorOrgs({ q: org, limit: 10 }, controller.signal)
      .then((result) => {
        const match = result.orgs.find((candidate) => candidate.slug === org);
        setOrgName({ slug: org, name: match?.name ?? org });
      })
      .catch(() => {
        if (!controller.signal.aborted) setOrgName({ slug: org, name: org });
      });
    return () => controller.abort();
  }, [api, org, orgName]);

  const orgLabel = org ? (orgName?.slug === org ? orgName.name : org) : null;

  // The bounds are recomputed per fetch, so "last 24 hours" means now.
  const viewKey = JSON.stringify([org, debouncedQuery, filter, range, from, to, mailSort, mailDir]);
  function currentQuery() {
    const bounds = rangeBounds(range, from, to);
    return {
      org,
      q: debouncedQuery,
      deliveryStatus: filter,
      since: bounds.since,
      until: bounds.until,
      sort: mailSort,
      dir: mailDir,
    };
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .listOperatorDeliveries({ ...currentQuery(), limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }, controller.signal)
      .then((result) => {
        setError(null);
        setData(result);
        setLoading(false);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(toApiError(err));
        setLoading(false);
      });
    return () => controller.abort();
    // currentQuery is derived from viewKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, viewKey, page, reloadToken]);

  // A new search goes back to page 1, like every other filter — but not on
  // mount, or a pasted `?page=3` would be thrown away.
  const searched = useRef(debouncedQuery);
  useEffect(() => {
    if (searched.current === debouncedQuery) return;
    searched.current = debouncedQuery;
    if (page !== 1) onParams({ page: 1 });
    // Only when the debounced text changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery]);

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const file = await api.exportOperatorDeliveries(currentQuery());
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.filename;
      link.click();
      URL.revokeObjectURL(url);
      onToast(
        file.truncated
          ? `Exported the first 10,000 of ${file.total.toLocaleString("en-US")} rows. Narrow the filters for the rest.`
          : `Exported ${file.total.toLocaleString("en-US")} rows.`,
      );
    } catch (err) {
      setExportError(toApiError(err).message);
    } finally {
      setExporting(false);
    }
  }

  function sortBy(column: DeliverySortValue) {
    const next = nextSort(mailSort, mailDir, column);
    onParams({ mailSort: next.sort, mailDir: next.dir, page: 1 });
  }

  const rows = data?.deliveries ?? null;
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const counts = data?.counts ?? {};

  return (
    <section className="min-w-0 space-y-4" aria-label="Email deliveries">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search recipient name, email or title"
          aria-label="Search deliveries"
          maxLength={200}
          className={`${inputClass} min-w-0 flex-1 basis-60`}
        />
        <OrgPicker
          onPick={(picked) => {
            setOrgName(picked);
            onParams({ org: picked.slug, page: 1 });
          }}
        />
        <select
          value={filter}
          onChange={(event) => onParams({ status: event.target.value as OperatorDeliveryFilter, page: 1 })}
          aria-label="Delivery status"
          className={`${inputClass} w-auto!`}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
              {counts[f.value] !== undefined ? ` (${counts[f.value]!.toLocaleString("en-US")})` : data ? " (0)" : ""}
            </option>
          ))}
        </select>
        <select
          value={range}
          onChange={(event) => onParams({ range: event.target.value as DateRange, page: 1 })}
          aria-label="Issued"
          className={`${inputClass} w-auto!`}
        >
          {DATE_RANGES.map((value) => (
            <option key={value} value={value}>
              {RANGE_LABEL[value]}
            </option>
          ))}
        </select>
        {range === "custom" ? (
          <span className="flex flex-wrap items-center gap-2 text-sm text-muted">
            <label className="flex items-center gap-2">
              From
              <input
                type="date"
                value={from ?? ""}
                max={to ?? undefined}
                onChange={(event) => onParams({ from: event.target.value || null, page: 1 })}
                className={`${inputClass} w-auto!`}
              />
            </label>
            <label className="flex items-center gap-2">
              to
              <input
                type="date"
                value={to ?? ""}
                min={from ?? undefined}
                onChange={(event) => onParams({ to: event.target.value || null, page: 1 })}
                className={`${inputClass} w-auto!`}
              />
            </label>
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
        {org ? (
          <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-accent-line bg-accent-wash py-0.5 pl-3 pr-1 text-accent">
            <span className="truncate">Org: {orgLabel}</span>
            <button
              type="button"
              onClick={() => onParams({ org: null, page: 1 })}
              aria-label={`Remove organization filter ${orgLabel}`}
              className="rounded-full p-1 hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              <CloseIcon />
            </button>
          </span>
        ) : (
          <span>Every organization.</span>
        )}
        <span className="ml-auto flex items-center gap-3">
          {data ? <span className="font-mono">{total.toLocaleString("en-US")} total</span> : null}
          <button
            type="button"
            onClick={() => void exportCsv()}
            disabled={exporting || !data || total === 0}
            className={`${buttonClass("secondary", "sm")} gap-2`}
          >
            {exporting ? <Spinner /> : null}
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </span>
      </div>
      {exportError ? <ErrorNote>Export failed: {exportError}</ErrorNote> : null}

      {error ? <ErrorNote>{error.message}</ErrorNote> : null}
      {rows === null && !error ? <Skeleton rows={6} /> : null}
      {rows && rows.length === 0 && !loading ? (
        <EmptyFiltered
          orgLabel={orgLabel}
          filter={filter}
          query={debouncedQuery}
          range={range}
          onClearOrg={() => onParams({ org: null, page: 1 })}
          onClearStatus={() => onParams({ status: "attempted", page: 1 })}
          onClearRange={() => onParams({ range: "all", from: null, to: null, page: 1 })}
        />
      ) : null}

      {rows && rows.length > 0 ? (
        <div
          aria-busy={loading}
          className={`overflow-x-auto rounded-xl border border-hair bg-surface transition-opacity ${loading ? "opacity-60" : ""}`}
        >
          <table className="w-full text-left text-sm">
            <thead className="border-b border-hair text-faint">
              <tr>
                <SortHeader label="Organization" column="org" sort={mailSort} dir={mailDir} onSort={sortBy} />
                <SortHeader label="Recipient" column="recipient" sort={mailSort} dir={mailDir} onSort={sortBy} />
                <SortHeader label="Credential" column="title" sort={mailSort} dir={mailDir} onSort={sortBy} />
                <SortHeader label="Email" column="status" sort={mailSort} dir={mailDir} onSort={sortBy} />
                <SortHeader label="Issued" column="issued_at" sort={mailSort} dir={mailDir} onSort={sortBy} />
                <SortHeader label="Sent at" column="delivered_at" sort={mailSort} dir={mailDir} onSort={sortBy} />
                <SortHeader
                  label="Attempts"
                  column="attempts"
                  sort={mailSort}
                  dir={mailDir}
                  onSort={sortBy}
                  align="right"
                />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-hair-soft align-top last:border-0">
                  <td className="px-4 py-3">
                    <span className="block text-ink">{row.org_name}</span>
                    <Mono className="text-xs text-faint">{row.org_slug}</Mono>
                  </td>
                  <td className="px-4 py-3">
                    <span className="block text-ink">
                      {row.recipient_name}
                      {row.possible_duplicate ? (
                        <QualityBadge title="The same org issued another credential to this name or email within 7 days.">
                          Possible dup
                        </QualityBadge>
                      ) : null}
                    </span>
                    <span className="text-xs text-muted">{row.recipient_email ?? "no address"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="block text-ink">
                      {row.title}
                      {row.title_looks_like_email ? (
                        <QualityBadge title="The title is an email address — likely a column mix-up in the upload.">
                          Title is email
                        </QualityBadge>
                      ) : null}
                    </span>
                    <Mono className="text-xs text-faint">{row.id}</Mono>
                    {row.is_test ? (
                      <span className="ml-2">
                        <StatusTag tone="warn">Test</StatusTag>
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <StatusTag tone={TONE[row.delivery_status]}>{LABEL[row.delivery_status]}</StatusTag>
                    {row.delivery_error ? (
                      <p
                        className={`mt-1 max-w-xs break-words text-xs ${
                          row.delivery_status === "deferred" ? "text-muted" : "text-danger"
                        }`}
                      >
                        {row.delivery_error}
                      </p>
                    ) : null}
                    {/* The action sits under the status it acts on, so it is
                        never in a column scrolled off the table's right edge. */}
                    {row.resendable ? (
                      <button
                        type="button"
                        onClick={() => setResending(row)}
                        aria-label={`Resend email to ${row.recipient_name}`}
                        className={`${buttonClass("secondary", "sm")} mt-2`}
                      >
                        Resend
                      </button>
                    ) : row.resend_refusal && STUCK.has(row.delivery_status) ? (
                      <p className="mt-1 max-w-xs text-xs text-muted">No resend: {row.resend_refusal}</p>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted" title={formatAbsolute(row.issued_at)}>
                    {formatDateTime(row.issued_at)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted">{formatDateTime(row.delivered_at)}</td>
                  <td className="px-4 py-3 text-right font-mono text-muted">{row.delivery_attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {data && total > PAGE_SIZE ? (
        <nav aria-label="Pages" className="flex flex-wrap items-center gap-3 text-sm text-muted">
          <button
            type="button"
            onClick={() => onParams({ page: page - 1 })}
            disabled={page <= 1 || loading}
            className={buttonClass("secondary", "sm")}
          >
            Previous
          </button>
          <span aria-live="polite">
            Page {Math.min(page, pages)} of {pages} · rows {((page - 1) * PAGE_SIZE + 1).toLocaleString("en-US")}–
            {Math.min(page * PAGE_SIZE, total).toLocaleString("en-US")}
          </span>
          <button
            type="button"
            onClick={() => onParams({ page: page + 1 })}
            disabled={page >= pages || loading}
            className={buttonClass("secondary", "sm")}
          >
            Next
          </button>
        </nav>
      ) : null}

      <ResendDialog
        delivery={resending}
        onCancel={() => setResending(null)}
        onDone={(result) => {
          const who = resending?.recipient_name ?? result.id;
          setResending(null);
          onToast(
            result.sent
              ? `Resent to ${who}. Attempt ${result.delivery.attempts}.`
              : `The provider refused the resend to ${who}: ${result.delivery.error ?? "no reason given"}.`,
          );
          setReloadToken((current) => current + 1);
        }}
      />
    </section>
  );
}

/** Names whatever is narrowing the list, with a way out of each. A bare
 *  "No credential matches these filters" hid which filter that was. */
function EmptyFiltered({
  orgLabel,
  filter,
  query,
  range,
  onClearOrg,
  onClearStatus,
  onClearRange,
}: {
  orgLabel: string | null;
  filter: OperatorDeliveryFilter;
  query: string;
  range: DateRange;
  onClearOrg: () => void;
  onClearStatus: () => void;
  onClearRange: () => void;
}) {
  const statusLabel = FILTERS.find((f) => f.value === filter)?.label ?? filter;
  const narrowedByStatus = filter !== "attempted";
  const subject = narrowedByStatus ? `${statusLabel.toLowerCase()} rows` : "emails";
  const where = [
    orgLabel ? `for ${orgLabel}` : null,
    query ? `matching “${query}”` : null,
    range !== "all" ? RANGE_LABEL[range].replace("…", "").toLowerCase() : null,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="rounded-lg border border-dashed border-hair-strong px-4 py-6 text-center text-sm text-faint">
      <p>
        No {subject}
        {where ? ` ${where}` : ""}.
      </p>
      {orgLabel || narrowedByStatus || range !== "all" ? (
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {orgLabel ? (
            <button type="button" onClick={onClearOrg} className={buttonClass("secondary", "sm")}>
              Clear filter
            </button>
          ) : null}
          {narrowedByStatus ? (
            <button type="button" onClick={onClearStatus} className={buttonClass("quiet", "sm")}>
              Show all emails
            </button>
          ) : null}
          {range !== "all" ? (
            <button type="button" onClick={onClearRange} className={buttonClass("quiet", "sm")}>
              Any time
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
