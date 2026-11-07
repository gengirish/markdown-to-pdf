"use client";

import { useEffect, useState } from "react";

import {
  toApiError,
  type ApiError,
  type DeliveryStatus,
  type OperatorDelivery,
  type OperatorDeliveryFilter,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { EmptyNote, ErrorNote, Mono, Skeleton, StatusTag, buttonClass, inputClass } from "@/components/dashboard/ui";

const PAGE_SIZE = 50;

const FILTERS: { value: OperatorDeliveryFilter; label: string }[] = [
  { value: "attempted", label: "All emails" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
  { value: "pending", label: "Pending" },
  { value: "unknown", label: "Unknown (pre-tracking)" },
  { value: "not_requested", label: "Not emailed" },
  { value: "all", label: "Every credential" },
];

const TONE: Record<DeliveryStatus, "ok" | "warn" | "neutral" | "bad"> = {
  sent: "ok",
  failed: "bad",
  pending: "warn",
  unknown: "neutral",
  not_requested: "neutral",
};

const LABEL: Record<DeliveryStatus, string> = {
  sent: "Sent",
  failed: "Failed",
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
 * Which org emailed which recipient, and what became of each send. Read-only:
 * the API is the operator-only `GET /api/v1/operator/deliveries`.
 */
export function DeliveriesPanel({
  org,
  onClearOrg,
}: {
  /** An org slug to narrow to, or null for every org. */
  org: string | null;
  onClearOrg: () => void;
}) {
  const api = useCertForge();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [filter, setFilter] = useState<OperatorDeliveryFilter>("attempted");
  const [rows, setRows] = useState<OperatorDelivery[] | null>(null);
  const [total, setTotal] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(null);
    api
      .listOperatorDeliveries(
        { org, q: debouncedQuery, deliveryStatus: filter, limit: PAGE_SIZE },
        controller.signal,
      )
      .then((page) => {
        setRows(page.deliveries);
        setTotal(page.total);
        setNextCursor(page.next_cursor);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(toApiError(err));
      });
    return () => controller.abort();
  }, [api, org, debouncedQuery, filter]);

  async function loadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const page = await api.listOperatorDeliveries({
        org,
        q: debouncedQuery,
        deliveryStatus: filter,
        limit: PAGE_SIZE,
        cursor: nextCursor,
      });
      setRows((current) => [...(current ?? []), ...page.deliveries]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search recipient name, email or title"
          aria-label="Search deliveries"
          maxLength={200}
          className={`${inputClass} min-w-0 flex-1`}
        />
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as OperatorDeliveryFilter)}
          aria-label="Delivery status"
          className={`${inputClass} w-auto`}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
        {org ? (
          <>
            <span>
              Organization: <Mono className="text-ink">{org}</Mono>
            </span>
            <button type="button" onClick={onClearOrg} className={buttonClass("secondary", "sm")}>
              Show every org
            </button>
          </>
        ) : (
          <span>Every organization. Pick one on the Plans tab to narrow this list.</span>
        )}
        {rows ? <span className="ml-auto font-mono">{total.toLocaleString("en-US")} total</span> : null}
      </div>

      {error ? <ErrorNote>{error.message}</ErrorNote> : null}
      {rows === null && !error ? <Skeleton rows={6} /> : null}
      {rows && rows.length === 0 ? <EmptyNote>No credential matches these filters.</EmptyNote> : null}

      {rows && rows.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-hair bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-hair text-faint">
              <tr>
                <th className="px-4 py-3 font-medium">Organization</th>
                <th className="px-4 py-3 font-medium">Recipient</th>
                <th className="px-4 py-3 font-medium">Credential</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Sent at</th>
                <th className="px-4 py-3 text-right font-medium">Attempts</th>
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
                    <span className="block text-ink">{row.recipient_name}</span>
                    <span className="text-xs text-muted">{row.recipient_email ?? "no address"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="block text-ink">{row.title}</span>
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
                      <p className="mt-1 max-w-xs break-words text-xs text-danger">{row.delivery_error}</p>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted">{formatDateTime(row.delivered_at)}</td>
                  <td className="px-4 py-3 text-right font-mono text-muted">{row.delivery_attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {nextCursor ? (
        <button
          type="button"
          onClick={() => void loadMore()}
          disabled={loadingMore}
          className={buttonClass("secondary", "sm")}
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      ) : null}
    </section>
  );
}
