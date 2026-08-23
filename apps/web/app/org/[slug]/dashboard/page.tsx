"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { SignInButton, useAuth } from "@clerk/nextjs";

import { publicApi, toApiError, type OrgProfile } from "@/lib/api";
import { ApiStatusBadge } from "@/components/dashboard/api-status-badge";
import { BulkIssueCard } from "@/components/dashboard/bulk-issue-card";
import { DeveloperCard } from "@/components/dashboard/developer-card";
import { RecentCredentialsCard } from "@/components/dashboard/recent-credentials-card";
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
          error.isNotFound ? `No organization with the slug “${slug}”.` : error.message,
        );
      });
    return () => controller.abort();
  }, [slug]);

  const handleIssued = useCallback(() => setIssuedToken((current) => current + 1), []);

  if (!isLoaded) {
    return <div className="min-h-screen bg-[#0a0a0a]" />;
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] p-6 font-sans text-zinc-100 sm:p-8">
      <header className="mx-auto mb-12 flex max-w-6xl flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="mb-2 text-3xl font-semibold tracking-tight text-white">
            Credential Studio
          </h1>
          <p className="text-zinc-400">
            {org ? org.name : slug}
            {org ? <span className="ml-2 text-zinc-600">· {org.tier} plan</span> : null}
          </p>
        </div>
        <ApiStatusBadge />
      </header>

      <main className="mx-auto max-w-6xl">
        {orgError ? (
          <div className="mb-8">
            <ErrorNote>{orgError}</ErrorNote>
          </div>
        ) : null}

        {!isSignedIn ? (
          <SignInPrompt slug={slug} />
        ) : (
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            <div className="space-y-8 lg:col-span-2">
              <BulkIssueCard slug={slug} onIssued={handleIssued} />
              <DeveloperCard slug={slug} />
            </div>

            <div className="space-y-8">
              <PlanCard org={org} />
              <RecentCredentialsCard slug={slug} refreshToken={issuedToken} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function SignInPrompt({ slug }: { slug: string }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 text-center">
      <h2 className="text-xl font-medium text-white">Sign in to continue</h2>
      <p className="mt-2 text-sm text-zinc-400">
        The Credential Studio for {slug} is only visible to members of the organization.
      </p>
      <div className="mt-6 flex flex-col gap-3">
        <SignInButton mode="modal">
          <button className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition-colors hover:bg-indigo-500">
            Sign in
          </button>
        </SignInButton>
        <Link href="/" className="text-sm text-zinc-500 transition-colors hover:text-zinc-300">
          Back to CertForge
        </Link>
      </div>
    </div>
  );
}

function PlanCard({ org }: { org: OrgProfile | null }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-indigo-500/20 bg-gradient-to-br from-indigo-900/40 to-purple-900/40 p-6">
      <div className="absolute right-0 top-0 h-32 w-32 rounded-full bg-indigo-500/20 blur-3xl" />
      <h3 className="relative mb-4 text-sm font-medium uppercase tracking-wider text-indigo-300">
        Plan
      </h3>
      <p className="relative text-3xl font-bold capitalize text-white">{org?.tier ?? "—"}</p>
      {/* No usage endpoint exists yet, and the checkout endpoint returns a
          placeholder URL server-side, so neither is surfaced as if it worked. */}
      <p className="relative mt-4 text-sm leading-relaxed text-zinc-300">
        Usage reporting and self-serve upgrades are not available yet. Contact support to change
        your plan or quota.
      </p>
    </section>
  );
}
