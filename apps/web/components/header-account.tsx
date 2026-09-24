"use client";

import Link from "next/link";
import { SignInButton, SignOutButton, UserButton, useAuth, useOrganization } from "@clerk/nextjs";

/**
 * The account controls at the right of a header: where the signed-in user
 * goes next, and how they leave.
 *
 * Sign-out is a labelled button rather than only an entry inside
 * `<UserButton>`'s menu — an avatar does not read as "log out" to someone
 * looking for it, and that is who this control exists for.
 *
 * `showStudioLink` is off in the dashboard's own header, where the Studio is
 * the page already on screen.
 */
export function HeaderAccount({ showStudioLink = true }: { showStudioLink?: boolean }) {
  const { isLoaded, isSignedIn } = useAuth();
  const { organization } = useOrganization();

  if (!isLoaded) {
    return <div className="h-8 w-24 animate-pulse rounded-lg bg-well" aria-hidden />;
  }

  if (!isSignedIn) {
    return (
      <SignInButton mode="modal">
        <button className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-well hover:text-ink">
          Sign in
        </button>
      </SignInButton>
    );
  }

  return (
    <div className="flex items-center gap-3">
      {showStudioLink && organization ? (
        <Link
          href={`/org/${organization.slug}/dashboard`}
          className="hidden max-w-[16rem] truncate rounded-lg lg:block bg-accent px-4 py-2 text-sm font-medium text-ground no-underline transition-colors hover:bg-accent-hover"
        >
          Open {organization.name} Studio
        </Link>
      ) : null}
      <UserButton />
      <SignOutButton redirectUrl="/">
        <button className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-well hover:text-ink">
          Sign out
        </button>
      </SignOutButton>
    </div>
  );
}
