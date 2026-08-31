"use client";

import Link from "next/link";
import { OrganizationSwitcher, SignInButton, SignUpButton, UserButton, useAuth, useOrganization } from "@clerk/nextjs";

/**
 * The landing page's auth-dependent call to action.
 *
 * Clerk v7 dropped the `<SignedIn>` / `<SignedOut>` control components. The
 * replacement `<Show>` resolves server-side; branching on the client hooks
 * keeps this working as a client island inside a static page, and avoids
 * making the whole landing page dynamic just to decide one button's label.
 */
export function AccountPanel() {
  const { isLoaded, isSignedIn } = useAuth();
  const { organization } = useOrganization();

  if (!isLoaded) {
    return <div className="h-[46px] w-56 animate-pulse rounded-lg bg-well" aria-hidden />;
  }

  if (!isSignedIn) {
    return (
      <div className="flex flex-col gap-3 sm:flex-row">
        <SignInButton mode="modal">
          <button className="rounded-lg bg-accent px-6 py-3 text-sm font-medium text-ground transition-colors hover:bg-accent-hover">
            Sign in
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="rounded-lg border border-hair-strong px-6 py-3 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent">
            Create an account
          </button>
        </SignUpButton>
      </div>
    );
  }

  if (!organization) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted">
          Pick an organization to open its Credential Studio.
        </p>
        <div className="rounded-lg border border-hair bg-surface p-2">
          <OrganizationSwitcher
            afterSelectOrganizationUrl="/org/:slug/dashboard"
            afterCreateOrganizationUrl="/org/:slug/dashboard"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-4">
      <Link
        href={`/org/${organization.slug}/dashboard`}
        className="rounded-lg bg-accent px-6 py-3 text-sm font-medium text-ground no-underline transition-colors hover:bg-accent-hover"
      >
        Open {organization.name} Studio
      </Link>
      <UserButton />
    </div>
  );
}
