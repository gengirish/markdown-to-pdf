"use client";

import { useEffect, useState } from "react";

import { toApiError, type ApiError, type OperatorOrgRow, type OperatorTier } from "@/lib/api";
import {
  formatAbsolute,
  formatLimit,
  formatRelative,
  nextSort,
  usageTone,
  type OperatorParams,
  type OrgSortValue,
} from "@/lib/operator";
import { useCertForge } from "@/lib/use-api";
import { EmptyNote, ErrorNote, Skeleton, StatusTag, buttonClass, inputClass } from "@/components/dashboard/ui";
import { CopySlug, QualityBadge, SortHeader, UsageBar } from "./bits";

const PAGE_SIZE = 25;

/**
 * The Plans tab's org list. Filters, sort and search are all applied by the
 * API (`GET /operator/orgs`), so a filter narrows every org rather than the
 * page already loaded. Filter and sort state is the page's, kept in the URL.
 */
export function OrgTable({
  params,
  onParams,
  selected,
  onSelect,
  tiers,
  reloadToken,
  compact,
  onForbidden,
}: {
  params: OperatorParams;
  onParams: (patch: Partial<OperatorParams>) => void;
  selected: string | null;
  onSelect: (slug: string, trigger: HTMLElement | null) => void;
  tiers: OperatorTier[] | null;
  reloadToken: number;
  /** The drawer is open beside the table: drop Last activity, which the drawer shows. */
  compact: boolean;
  /** The API said 403: the page swaps the console for its explanation. */
  onForbidden: () => void;
}) {
  const api = useCertForge();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [orgs, setOrgs] = useState<OperatorOrgRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  const filterKey = JSON.stringify([
    debouncedQuery,
    params.plans,
    params.active,
    params.near,
    params.override,
    params.orgSort,
    params.orgDir,
  ]);
  const listQuery = {
    q: debouncedQuery,
    tiers: params.plans,
    active: params.active,
    nearLimit: params.near,
    hasOverride: params.override,
    sort: params.orgSort,
    dir: params.orgDir,
    limit: PAGE_SIZE,
  };

  useEffect(() => {
    const controller = new AbortController();
    api
      .listOperatorOrgs(listQuery, controller.signal)
      .then((page) => {
        setError(null);
        setOrgs(page.orgs);
        setTotal(page.total);
        setNextCursor(page.next_cursor);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        const apiError = toApiError(err);
        if (apiError.isForbidden) onForbidden();
        setError(apiError);
      });
    return () => controller.abort();
    // listQuery is derived from filterKey; listing it would refetch every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, filterKey, reloadToken]);

  async function loadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const page = await api.listOperatorOrgs({ ...listQuery, cursor: nextCursor });
      setOrgs((current) => [...(current ?? []), ...page.orgs]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setLoadingMore(false);
    }
  }

  function sortBy(column: OrgSortValue) {
    const next = nextSort(params.orgSort, params.orgDir, column);
    onParams({ orgSort: next.sort, orgDir: next.dir });
  }

  const anyFilter = params.plans.length > 0 || params.active || params.near || params.override;
  const now = new Date();
  // Hidden only beside the drawer below xl, where it would push Used / limit off screen.
  // Beside the drawer the table has ~45rem; Last activity is also in the
  // drawer, so it gives its width to the name rather than crushing it.
  const lastActivityCol = compact ? "hidden" : "";

  return (
    <section className="min-w-0 space-y-4" aria-label="Organizations">
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search by slug or name"
        aria-label="Search organizations"
        maxLength={100}
        className={inputClass}
      />

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
        {(tiers ?? []).map((tier) => {
          const on = params.plans.includes(tier.key);
          return (
            <Chip
              key={tier.key}
              pressed={on}
              onClick={() =>
                onParams({ plans: on ? params.plans.filter((key) => key !== tier.key) : [...params.plans, tier.key] })
              }
            >
              {tier.name}
            </Chip>
          );
        })}
        <span aria-hidden className="mx-1 h-5 w-px bg-hair" />
        <Chip pressed={params.active} onClick={() => onParams({ active: !params.active })}>
          Active this month
        </Chip>
        <Chip pressed={params.near} onClick={() => onParams({ near: !params.near })}>
          Near limit (≥ 80%)
        </Chip>
        <Chip pressed={params.override} onClick={() => onParams({ override: !params.override })}>
          Has override
        </Chip>
        {anyFilter ? (
          <button
            type="button"
            onClick={() => onParams({ plans: [], active: false, near: false, override: false })}
            className={buttonClass("quiet", "sm")}
          >
            Clear filters
          </button>
        ) : null}
        {orgs ? (
          <span className="ml-auto font-mono text-sm text-muted">{total.toLocaleString("en-US")} orgs</span>
        ) : null}
      </div>

      {error ? <ErrorNote>{error.message}</ErrorNote> : null}
      {orgs === null && !error ? <Skeleton rows={5} /> : null}
      {orgs && orgs.length === 0 ? (
        <EmptyNote>
          {debouncedQuery
            ? `No organization matches “${debouncedQuery}”${anyFilter ? " with these filters" : ""}.`
            : anyFilter
              ? "No organization matches these filters."
              : "There are no organizations."}
        </EmptyNote>
      ) : null}

      {orgs && orgs.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-hair bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-hair text-faint">
              <tr>
                <SortHeader label="Organization" column="name" sort={params.orgSort} dir={params.orgDir} onSort={sortBy} />
                <SortHeader label="Plan" column="plan" sort={params.orgSort} dir={params.orgDir} onSort={sortBy} />
                <SortHeader
                  label="Enforced limit"
                  column="limit"
                  sort={params.orgSort}
                  dir={params.orgDir}
                  onSort={sortBy}
                  align="right"
                />
                <SortHeader
                  label="Used / limit"
                  column="usage"
                  sort={params.orgSort}
                  dir={params.orgDir}
                  onSort={sortBy}
                  align="right"
                />
                <SortHeader
                  label="Last activity"
                  column="last_activity"
                  sort={params.orgSort}
                  dir={params.orgDir}
                  onSort={sortBy}
                  align="right"
                  className={lastActivityCol}
                />
              </tr>
            </thead>
            <tbody>
              {orgs.map((org) => {
                const tone = usageTone(org.usage_percent);
                const usedColor = tone === "bad" ? "text-danger" : tone === "warn" ? "text-warn-ink" : "text-ink";
                return (
                  <tr
                    key={org.slug}
                    onClick={(event) => onSelect(org.slug, event.currentTarget.querySelector("button"))}
                    className={`cursor-pointer border-b border-hair-soft last:border-0 hover:bg-well ${
                      selected === org.slug ? "bg-well" : ""
                    }`}
                  >
                    {/* A floor on the name: `max-w-0` alone let the other
                        columns take everything, and names rendered as "I.". */}
                    <td className="px-4 py-3">
                      <div className="flex min-w-44 max-w-80 items-center gap-1">
                        {/* A real button so the row is reachable by keyboard. */}
                        <button
                          type="button"
                          aria-current={selected === org.slug ? "true" : undefined}
                          onClick={(event) => {
                            event.stopPropagation();
                            onSelect(org.slug, event.currentTarget);
                          }}
                          className="min-w-0 truncate text-left text-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                        >
                          {org.name}
                        </button>
                        <CopySlug slug={org.slug} />
                        {org.duplicate_name ? (
                          <QualityBadge title="Another organization has the same display name.">Dup name</QualityBadge>
                        ) : null}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted">
                      {org.tier_name}
                      {org.tier_known ? null : <span className="ml-1 text-warn-ink">({org.tier}?)</span>}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-ink">
                      {org.override ? (
                        <span className="mr-2 align-middle">
                          <StatusTag tone="ok">override</StatusTag>
                        </span>
                      ) : null}
                      <span title={org.override ? `Plan limit ${formatLimit(org.tier_quota)}` : undefined}>
                        {formatLimit(org.effective)}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-mono">
                      <span className={usedColor}>
                        {org.used.toLocaleString("en-US")} / {formatLimit(org.effective)}
                      </span>
                      <UsageBar percent={org.usage_percent} tone={tone} />
                    </td>
                    <td
                      className={`whitespace-nowrap px-4 py-3 text-right text-muted ${lastActivityCol}`}
                      title={formatAbsolute(org.last_activity_at) || undefined}
                    >
                      {formatRelative(org.last_activity_at, now)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {nextCursor ? (
        <button type="button" onClick={() => void loadMore()} disabled={loadingMore} className={buttonClass("secondary", "sm")}>
          {loadingMore ? "Loading…" : `Load more (${(total - (orgs?.length ?? 0)).toLocaleString("en-US")} left)`}
        </button>
      ) : null}
    </section>
  );
}

function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
        pressed ? "border-accent-line bg-accent-wash text-accent" : "border-hair text-muted hover:border-hair-strong hover:text-ink"
      }`}
    >
      {pressed ? <span aria-hidden>✓ </span> : null}
      {children}
    </button>
  );
}
