"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth, useUser } from "@clerk/nextjs";

import { publicApi, toApiError, type ApiError, type OperatorOrg, type Tier } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { HeaderAccount } from "@/components/header-account";
import { ThemeToggle } from "@/components/theme-toggle";
import { formatLimit, QuotaPanel } from "@/components/operator/quota-panel";
import { EmptyNote, ErrorNote, Mono, Skeleton, StatusTag, buttonClass, inputClass } from "@/components/dashboard/ui";

const PAGE_SIZE = 25;

/**
 * CertForge staff: find an org, then give it its own credential limit or move
 * it to another plan. docs/operator-quota-overrides-plan.md, W3.
 *
 * Who may use it is decided by the API alone (`require_operator`, an allowlist
 * of Clerk user ids). This page renders whatever the API says, including a 403,
 * which it explains rather than showing an empty table. There is no nav link;
 * operators bookmark the URL.
 */
export default function OperatorPage() {
  const api = useCertForge();
  const { isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [orgs, setOrgs] = useState<OperatorOrg[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [tiers, setTiers] = useState<Tier[] | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    const controller = new AbortController();
    setOrgs(null);
    setError(null);
    api
      .listOperatorOrgs({ q: debouncedQuery, limit: PAGE_SIZE }, controller.signal)
      .then((page) => {
        setOrgs(page.orgs);
        setNextCursor(page.next_cursor);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(toApiError(err));
      });
    return () => controller.abort();
  }, [api, debouncedQuery, isLoaded, isSignedIn]);

  // The plan control needs the catalog; without it the panel just hides that control.
  useEffect(() => {
    const controller = new AbortController();
    publicApi
      .listTiers(controller.signal)
      .then(setTiers)
      .catch(() => {
        if (!controller.signal.aborted) setTiers(null);
      });
    return () => controller.abort();
  }, []);

  async function loadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const page = await api.listOperatorOrgs({ q: debouncedQuery, limit: PAGE_SIZE, cursor: nextCursor });
      setOrgs((current) => [...(current ?? []), ...page.orgs]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setLoadingMore(false);
    }
  }

  function handleChanged(updated: OperatorOrg) {
    setOrgs((current) => current?.map((org) => (org.slug === updated.slug ? updated : org)) ?? current);
  }

  if (!isLoaded) {
    return <div className="min-h-screen bg-ground" />;
  }

  const forbidden = error?.isForbidden ?? false;

  return (
    <div className="min-h-screen bg-ground p-6 font-sans text-ink sm:p-8">
      <header className="mx-auto mb-10 flex max-w-6xl flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/"
            className="mb-4 inline-flex items-center gap-2 text-sm text-muted no-underline transition-colors hover:text-ink"
          >
            <span className="flex h-[18px] w-[18px] items-center justify-center rounded bg-accent text-[10px] font-bold text-ground">
              C
            </span>
            CertForge home
          </Link>
          <h1 className="mb-2 text-3xl font-semibold tracking-tight text-ink">Operator</h1>
          <p className="text-muted">Per-org credential limits and plans. Every change is logged with a reason.</p>
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <HeaderAccount showStudioLink={false} accountMenu />
        </div>
      </header>

      <main className="mx-auto max-w-6xl">
        {!isSignedIn ? (
          <ErrorNote>Sign in to use this page.</ErrorNote>
        ) : forbidden ? (
          <div className="max-w-2xl space-y-3">
            <ErrorNote>Your account is not a CertForge operator, so the API refused the request (403).</ErrorNote>
            <p className="text-sm leading-relaxed text-muted">
              Operators are an allowlist of Clerk user ids in the API&apos;s{" "}
              <Mono>CERTFORGE_OPERATOR_USER_IDS</Mono> secret. If you should have access, ask someone with Fly
              access to add your id
              {user ? (
                <>
                  {" "}(<Mono className="text-ink">{user.id}</Mono>)
                </>
              ) : null}{" "}
              and restart the API.
            </p>
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
            <section className="min-w-0 space-y-4">
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by slug or name"
                aria-label="Search organizations"
                maxLength={100}
                className={inputClass}
              />

              {error ? <ErrorNote>{error.message}</ErrorNote> : null}
              {orgs === null && !error ? <Skeleton rows={5} /> : null}
              {orgs && orgs.length === 0 ? (
                <EmptyNote>{debouncedQuery ? `No organization matches “${debouncedQuery}”.` : "There are no organizations."}</EmptyNote>
              ) : null}

              {orgs && orgs.length > 0 ? (
                <div className="overflow-x-auto rounded-xl border border-hair bg-surface">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-hair text-faint">
                      <tr>
                        <th className="px-4 py-3 font-medium">Organization</th>
                        <th className="px-4 py-3 font-medium">Plan</th>
                        <th className="px-4 py-3 text-right font-medium">Plan limit</th>
                        <th className="px-4 py-3 text-right font-medium">Override</th>
                        <th className="px-4 py-3 text-right font-medium">Used / limit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orgs.map((org) => {
                        const over = org.effective !== null && org.used >= org.effective;
                        return (
                          <tr
                            key={org.slug}
                            onClick={() => setSelected(org.slug)}
                            className={`cursor-pointer border-b border-hair-soft last:border-0 hover:bg-well ${
                              selected === org.slug ? "bg-well" : ""
                            }`}
                          >
                            <td className="px-4 py-3">
                              {/* A real button so the row is reachable by keyboard. */}
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelected(org.slug);
                                }}
                                className="text-left"
                              >
                                <span className="block text-ink">{org.name}</span>
                                <Mono className="text-xs text-faint">{org.slug}</Mono>
                              </button>
                            </td>
                            <td className="px-4 py-3 text-muted">
                              {org.tier_name}
                              {org.tier_known ? null : <span className="ml-1 text-warn-ink">({org.tier}?)</span>}
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-muted">{formatLimit(org.tier_quota)}</td>
                            <td className="px-4 py-3 text-right">
                              {org.override ? (
                                <StatusTag tone="ok">{formatLimit(org.override.limit)}</StatusTag>
                              ) : (
                                <span className="text-faint">—</span>
                              )}
                            </td>
                            <td className={`px-4 py-3 text-right font-mono ${over ? "text-danger" : "text-ink"}`}>
                              {org.used.toLocaleString("en-US")} / {formatLimit(org.effective)}
                            </td>
                          </tr>
                        );
                      })}
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

            <div className="min-w-0">
              {selected ? (
                <QuotaPanel
                  key={selected}
                  slug={selected}
                  tiers={tiers}
                  onChanged={handleChanged}
                  onClose={() => setSelected(null)}
                />
              ) : orgs && orgs.length > 0 ? (
                <EmptyNote>Pick an organization to change its limit.</EmptyNote>
              ) : null}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
