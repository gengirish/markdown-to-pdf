"use client";

import Link from "next/link";
import { OrganizationSwitcher, SignInButton, SignUpButton, UserButton, useAuth, useOrganization } from "@clerk/nextjs";

/**
 * The landing page's auth-dependent call to action.
 *
 * Clerk v7 dropped the `<SignedIn>` / `<SignedOut>` control components, and the
 * replacement `<Show>` resolves server-side (so it needs `clerkMiddleware`,
 * which this app does not install yet). Branching on the client hooks keeps the
 * page working with nothing but `<ClerkProvider>`.
 */
export function AccountPanel() {
  const { isLoaded, isSignedIn } = useAuth();
  const { organization } = useOrganization();

  if (!isLoaded) {
    return <div className="h-12 w-56 animate-pulse rounded-lg bg-zinc-900" aria-hidden />;
  }

  if (!isSignedIn) {
    return (
      <div className="flex flex-col gap-3 sm:flex-row">
        <SignInButton mode="modal">
          <button className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500">
            Sign in
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="rounded-lg border border-zinc-700 px-6 py-3 font-medium text-zinc-200 transition-colors hover:bg-zinc-800">
            Create an account
          </button>
        </SignUpButton>
      </div>
    );
  }

  if (!organization) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-zinc-400">
          Pick an organization to open its Credential Studio.
        </p>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2">
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
        className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition-colors hover:bg-indigo-500"
      >
        Open {organization.name} Studio
      </Link>
      <UserButton />
    </div>
  );
}
