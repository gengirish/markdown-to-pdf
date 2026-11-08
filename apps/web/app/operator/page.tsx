"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useAuth, useUser } from "@clerk/nextjs";

import { toApiError, type OperatorTier } from "@/lib/api";
import { operatorSearch, parseOperatorParams, tabDefaults, type OperatorParams } from "@/lib/operator";
import { useCertForge } from "@/lib/use-api";
import { HeaderAccount } from "@/components/header-account";
import { ThemeToggle } from "@/components/theme-toggle";
import { QuotaPanel } from "@/components/operator/quota-panel";
import { DeliveriesPanel } from "@/components/operator/deliveries-panel";
import { KpiStrip, type KpiKey } from "@/components/operator/kpi-strip";
import { OrgTable } from "@/components/operator/org-table";
import { Toast } from "@/components/operator/bits";
import { ErrorNote, Mono, buttonClass } from "@/components/dashboard/ui";

/** `useSearchParams` needs a Suspense boundary for the static prerender. */
export default function OperatorPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-ground" />}>
      <OperatorConsole />
    </Suspense>
  );
}

/**
 * CertForge staff console. docs/operator-quota-overrides-plan.md (W3) and
 * docs/operator-console-plan.md.
 *
 * Who may use it is decided by the API alone (`require_operator`, an allowlist
 * of Clerk user ids). This page renders whatever the API says, including a 403,
 * which it explains rather than showing an empty table. There is no nav link;
 * operators bookmark the URL.
 *
 * Every view is a URL: tab, filters, sort and page live in the query string
 * (`?tab=emails&org=acme&status=failed`), so a view can be shared and
 * survives a reload. A tab switch starts that tab from its defaults; the org
 * crosses tabs only through "View this org's emails" — an org picked on Plans
 * used to narrow Emails invisibly, which read as "0 total" and broken.
 */
function OperatorConsole() {
  const api = useCertForge();
  const { isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const searchParams = useSearchParams();
  const params = parseOperatorParams(searchParams);

  // Next keeps useSearchParams in step with history.pushState/replaceState.
  const navigate = useCallback((next: OperatorParams, mode: "push" | "replace" = "replace") => {
    const url = `${window.location.pathname}${operatorSearch(next)}`;
    if (mode === "push") window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
  }, []);

  // Read fresh from the URL each call, so two patches in one tick compose.
  const patch = useCallback(
    (changes: Partial<OperatorParams>) => {
      const current = parseOperatorParams(new URLSearchParams(window.location.search));
      navigate({ ...current, ...changes });
    },
    [navigate],
  );

  const view = params.tab;
  const selected = view === "plans" ? params.org : null;

  const [forbidden, setForbidden] = useState(false);
  const [tiers, setTiers] = useState<OperatorTier[] | null>(null);
  const [tiersError, setTiersError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  // Bumped after a write, so the table and the KPI strip re-read.
  const [reloadToken, setReloadToken] = useState(0);
  // Where focus goes back to when the drawer closes.
  const lastTrigger = useRef<HTMLElement | null>(null);

  const closeDrawer = useCallback(() => {
    patch({ org: null });
    const trigger = lastTrigger.current;
    if (trigger && document.contains(trigger)) trigger.focus();
  }, [patch]);

  // Esc closes the drawer — unless a modal is open, which Esc closes first.
  useEffect(() => {
    if (!selected) return;
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (document.querySelector("dialog[open]")) return;
      closeDrawer();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected, closeDrawer]);

  // The operator catalog, not the public one: the public one hides Scale.
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    const controller = new AbortController();
    api
      .listOperatorTiers(controller.signal)
      .then((data) => {
        setTiersError(null);
        setTiers(data);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        const apiError = toApiError(err);
        if (apiError.isForbidden) setForbidden(true);
        setTiersError(apiError.message);
      });
    return () => controller.abort();
  }, [api, isLoaded, isSignedIn]);

  function switchTab(tab: OperatorParams["tab"]) {
    if (view !== tab) navigate(tabDefaults(tab), "push");
  }

  const activeKpi: KpiKey | null =
    view !== "plans"
      ? null
      : params.near
        ? "near"
        : params.active && params.orgSort === "used"
          ? "issued"
          : params.active
            ? "active"
            : null;

  function pickKpi(key: KpiKey) {
    if (key === "failed") {
      navigate({ ...tabDefaults("emails"), status: "failed", range: "7d" }, "push");
      return;
    }
    // A pressed card is a toggle: clicking it again clears its filter.
    if (key === activeKpi) {
      patch({ active: false, near: false, orgSort: "usage", orgDir: "desc" });
      return;
    }
    const base = { plans: [], override: false, orgDir: "desc" as const };
    if (key === "active") patch({ ...base, active: true, near: false, orgSort: "usage" });
    if (key === "issued") patch({ ...base, active: true, near: false, orgSort: "used" });
    if (key === "near") patch({ ...base, active: false, near: true, orgSort: "usage" });
  }

  if (!isLoaded) {
    return <div className="min-h-screen bg-ground" />;
  }

  return (
    <div className="min-h-screen bg-ground p-4 font-sans text-ink sm:p-8">
      <header className="mx-auto mb-8 flex max-w-6xl flex-wrap items-start justify-between gap-4">
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
          <p className="text-muted">
            Who is near their limit, what failed to send, and what needs action. Every change is logged with who
            made it.
          </p>
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
          <>
            <div role="tablist" aria-label="Operator views" className="mb-6 flex gap-2">
              {(
                [
                  ["plans", "Plans & limits"],
                  ["emails", "Email deliveries"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={view === id}
                  onClick={() => switchTab(id)}
                  className={buttonClass(view === id ? "primary" : "secondary", "sm")}
                >
                  {label}
                </button>
              ))}
            </div>

            {view === "emails" ? (
              <DeliveriesPanel params={params} onParams={patch} onToast={setToast} />
            ) : (
              <>
                <KpiStrip active={activeKpi} onPick={pickKpi} reloadToken={reloadToken} />
                <div className={`grid gap-6 ${selected ? "lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]" : ""}`}>
                  <OrgTable
                    params={params}
                    onParams={patch}
                    selected={selected}
                    onSelect={(slug, trigger) => {
                      lastTrigger.current = trigger;
                      patch({ org: slug });
                    }}
                    tiers={tiers}
                    reloadToken={reloadToken}
                    compact={selected !== null}
                    onForbidden={() => setForbidden(true)}
                  />

                  {selected ? (
                    <>
                      {/* Below lg the drawer is a sheet over the table, with a backdrop. */}
                      <div aria-hidden className="fixed inset-0 z-30 bg-ink/30 lg:hidden" onClick={closeDrawer} />
                      <div className="fixed inset-y-0 right-0 z-40 w-full max-w-md lg:static lg:z-auto lg:max-w-none">
                        <QuotaPanel
                          key={selected}
                          slug={selected}
                          tiers={tiers}
                          tiersError={tiersError}
                          onChanged={() => setReloadToken((current) => current + 1)}
                          onClose={closeDrawer}
                          onToast={setToast}
                          onViewEmails={() => navigate({ ...tabDefaults("emails"), org: selected }, "push")}
                        />
                      </div>
                    </>
                  ) : null}
                </div>
              </>
            )}
          </>
        )}
      </main>
      <Toast message={toast} onDismiss={dismissToast} />
    </div>
  );
}
