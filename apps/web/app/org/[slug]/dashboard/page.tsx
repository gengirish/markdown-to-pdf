"use client";

import { use, useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SignInButton, useAuth } from "@clerk/nextjs";

import { publicApi, toApiError, type OrgProfile } from "@/lib/api";
import { ApiStatusBadge } from "@/components/dashboard/api-status-badge";
import { HeaderAccount } from "@/components/header-account";
import { ThemeToggle } from "@/components/theme-toggle";
import { BrandingCard } from "@/components/dashboard/branding-card";
import { IssueWizard } from "@/components/dashboard/issue-wizard";
import { DeveloperCard } from "@/components/dashboard/developer-card";
import { OverviewCard } from "@/components/dashboard/overview-card";
import { PlanCard } from "@/components/dashboard/plan-card";
import { RecentCredentialsCard } from "@/components/dashboard/recent-credentials-card";
import { CredentialsCard } from "@/components/dashboard/credentials-card";
import { SetupChecklist } from "@/components/dashboard/setup-checklist";
import { SingleIssueCard } from "@/components/dashboard/single-issue-card";
import { TemplatesCard } from "@/components/dashboard/templates-card";
import { ErrorNote } from "@/components/dashboard/ui";

export default function OrgDashboard({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const { isLoaded, isSignedIn } = useAuth();

  const [org, setOrg] = useState<OrgProfile | null>(null);
  const [orgError, setOrgError] = useState<string | null>(null);
  // Bumped when a batch settles so the credential list refetches.
  const [issuedToken, setIssuedToken] = useState(0);

  // The org profile endpoint is public, so the header renders even while Clerk
  // is still loading and even for a viewer who turns out not to be a member.
  useEffect(() => {
    const controller = new AbortController();
    publicApi
      .getOrg(slug, controller.signal)
      .then((profile) => {
        setOrg(profile);
        setOrgError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        const error = toApiError(err);
        setOrgError(
          error.isNotFound
            ? "This organization does not exist, or its address has changed."
            : error.message,
        );
      });
    return () => controller.abort();
  }, [slug]);

  const handleIssued = useCallback(() => setIssuedToken((current) => current + 1), []);

  // The tab lives in the URL so a section can be linked to and Back works.
  // Other params are kept: billing returns here with `?checkout=complete`.
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  // Dodo's return URL names no tab; the plan card is where its outcome shows.
  const activeTab: TabId = isTabId(requestedTab)
    ? requestedTab
    : searchParams.get("checkout")
      ? "plan"
      : "overview";
  const selectTab = useCallback(
    (tab: TabId) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set("tab", tab);
      window.history.pushState(null, "", `?${next.toString()}`);
    },
    [searchParams],
  );

  if (!isLoaded) {
    return <div className="min-h-screen bg-ground" />;
  }

  return (
    <div className="min-h-screen bg-ground p-6 font-sans text-ink sm:p-8">
      <header className="mx-auto mb-12 flex max-w-6xl flex-wrap items-start justify-between gap-4">
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
          <h1 className="mb-2 text-3xl font-semibold tracking-tight text-ink">
            Credential Studio
          </h1>
          {/* Never the slug: it is an address, often an auto-generated one
              like `acme-s-organization-1790…`, not a name. A placeholder bar
              holds the line until the real name arrives. */}
          <p className="min-h-6 text-muted">
            {org ? (
              <>
                {org.name}
                <span className="ml-2 text-faint">· {org.tier} plan</span>
              </>
            ) : orgError ? null : (
              <>
                <span
                  aria-hidden
                  className="inline-block h-4 w-56 animate-pulse rounded bg-well align-middle"
                />
                <span className="sr-only">Loading organization</span>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ApiStatusBadge />
          <ThemeToggle />
          <HeaderAccount showStudioLink={false} />
        </div>
      </header>

      <main className="mx-auto max-w-6xl">
        {orgError ? (
          <div className="mb-8">
            <ErrorNote>{orgError}</ErrorNote>
          </div>
        ) : null}

        {!isSignedIn ? (
          <SignInPrompt orgName={org?.name ?? null} />
        ) : (
          <>
            {/* Refetches on a settled batch and on every tab change — the
                templates card has no callback, and leaving its tab is the
                moment a new template can have appeared. */}
            {orgError ? null : (
              <SetupChecklist
                key={slug}
                slug={slug}
                org={org}
                refreshKey={`${issuedToken}:${activeTab}`}
                onSelectTab={selectTab}
              />
            )}
            <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
              <SectionNav active={activeTab} onSelect={selectTab} />

              {/* Every panel stays mounted and is only hidden. Unmounting would
                  throw away a half-reviewed bulk upload the moment somebody
                  glanced at another tab, and the credential list has to be
                  mounted to hear `issuedToken` when a batch settles. */}
              <div className="min-w-0 flex-1">
                <TabPanel id="overview" active={activeTab}>
                  <OverviewCard
                    slug={slug}
                    refreshToken={issuedToken}
                    onViewCredentials={() => selectTab("credentials")}
                    onViewPlan={() => selectTab("plan")}
                  />
                  <RecentCredentialsCard slug={slug} refreshToken={issuedToken} limit={5} />
                </TabPanel>
                <TabPanel id="issue" active={activeTab}>
                  <SingleIssueCard slug={slug} onIssued={handleIssued} />
                  <IssueWizard slug={slug} onIssued={handleIssued} />
                </TabPanel>
                <TabPanel id="credentials" active={activeTab}>
                  <CredentialsCard slug={slug} refreshToken={issuedToken} />
                </TabPanel>
                <TabPanel id="templates" active={activeTab}>
                  <TemplatesCard slug={slug} />
                </TabPanel>
                <TabPanel id="branding" active={activeTab}>
                  <BrandingCard slug={slug} org={org} onSaved={setOrg} />
                </TabPanel>
                <TabPanel id="developers" active={activeTab}>
                  <DeveloperCard slug={slug} />
                </TabPanel>
                <TabPanel id="plan" active={activeTab}>
                  <PlanCard slug={slug} />
                </TabPanel>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "issue", label: "Issue" },
  { id: "credentials", label: "Credentials" },
  { id: "templates", label: "Templates" },
  { id: "branding", label: "Branding" },
  { id: "developers", label: "Developers" },
  { id: "plan", label: "Plan & usage" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTabId(value: string | null): value is TabId {
  return TABS.some((tab) => tab.id === value);
}

/** Sidebar on wide screens, a horizontally scrolling strip on narrow ones. */
function SectionNav({ active, onSelect }: { active: TabId; onSelect: (tab: TabId) => void }) {
  return (
    <nav
      aria-label="Credential Studio sections"
      className="-mx-6 overflow-x-auto px-6 sm:-mx-8 sm:px-8 lg:sticky lg:top-8 lg:mx-0 lg:w-52 lg:shrink-0 lg:overflow-visible lg:px-0"
    >
      <ul className="flex gap-1 lg:flex-col">
        {TABS.map((tab) => {
          const current = tab.id === active;
          return (
            <li key={tab.id} className="shrink-0">
              <button
                type="button"
                onClick={() => onSelect(tab.id)}
                aria-current={current ? "page" : undefined}
                className={`w-full whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  current
                    ? "bg-surface font-medium text-ink shadow-[var(--cf-shadow-card)] ring-1 ring-hair"
                    : "text-muted hover:bg-surface hover:text-ink"
                }`}
              >
                {tab.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function TabPanel({ id, active, children }: { id: TabId; active: TabId; children: ReactNode }) {
  return (
    <div hidden={id !== active} className="space-y-8">
      {children}
    </div>
  );
}

function SignInPrompt({ orgName }: { orgName: string | null }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-hair bg-surface p-8 text-center">
      <h2 className="text-xl font-medium text-ink">Sign in to continue</h2>
      <p className="mt-2 text-sm text-muted">
        The Credential Studio for {orgName ?? "this organization"} is only visible to members
        of the organization.
      </p>
      <div className="mt-6 flex flex-col gap-3">
        <SignInButton mode="modal">
          <button className="w-full rounded-lg bg-accent px-4 py-3 font-medium text-ground transition-colors hover:bg-accent-hover">
            Sign in
          </button>
        </SignInButton>
        <Link href="/" className="text-sm text-faint transition-colors hover:text-ink">
          Back to CertForge
        </Link>
      </div>
    </div>
  );
}

