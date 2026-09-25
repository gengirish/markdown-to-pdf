"use client";

import Link from "next/link";
import {
  SignInButton,
  SignOutButton,
  UserButton,
  useAuth,
  useClerk,
  useOrganization,
} from "@clerk/nextjs";

import { SettingsIcon } from "@/components/dashboard/icons";

/**
 * The account controls at the right of a header: where the signed-in user
 * goes next, and how they leave.
 *
 * Sign-out is a labelled button rather than only an entry inside
 * `<UserButton>`'s menu — an avatar does not read as "log out" to someone
 * looking for it, and that is who this control exists for.
 *
 * `showStudioLink` is off in the dashboard's own header, where the Studio is
 * the page already on screen. Everywhere else, signing in goes to
 * `/dashboard`; on a Studio page it stays put, since that org is the one the
 * visitor came for.
 *
 * `accountMenu` is the dashboard's variant (CF-07): no labelled Sign out
 * beside the avatar, because the Studio header had grown five controls wide.
 * Sign out, the account profile and the organization's settings all live in
 * the avatar's menu instead. Public pages keep the labelled button, for the
 * reason above — a visitor there is likelier to be looking for the way out.
 */
export function HeaderAccount({
  showStudioLink = true,
  accountMenu = false,
}: {
  showStudioLink?: boolean;
  accountMenu?: boolean;
}) {
  const { isLoaded, isSignedIn } = useAuth();
  const { organization } = useOrganization();
  const clerk = useClerk();
  const afterSignIn = showStudioLink ? "/dashboard" : undefined;

  if (!isLoaded) {
    return <div className="h-8 w-24 animate-pulse rounded-lg bg-well" aria-hidden />;
  }

  if (!isSignedIn) {
    return (
      <SignInButton
        mode="modal"
        forceRedirectUrl={afterSignIn}
        signUpForceRedirectUrl={afterSignIn}
      >
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
      {/* UserButton renders nothing until Clerk's UI bundle arrives, then a
          28px avatar. The fixed slot keeps the row from shifting when it
          does; the avatar paints over the placeholder circle. */}
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-well">
        {accountMenu ? (
          <UserButton>
            <UserButton.MenuItems>
              <UserButton.Action label="manageAccount" />
              {organization ? (
                <UserButton.Action
                  label="Organization settings"
                  labelIcon={<SettingsIcon />}
                  onClick={() => clerk.openOrganizationProfile()}
                />
              ) : null}
              <UserButton.Action label="signOut" />
            </UserButton.MenuItems>
          </UserButton>
        ) : (
          <UserButton />
        )}
      </span>
      {accountMenu ? null : (
        <SignOutButton redirectUrl="/">
          <button className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-well hover:text-ink">
            Sign out
          </button>
        </SignOutButton>
      )}
    </div>
  );
}
