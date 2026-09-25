"use client";

import { useState, useSyncExternalStore } from "react";
import { useClerk, useOrganization } from "@clerk/nextjs";

import { looksAutoNamed } from "@/lib/org-name";

/** A one-time nudge for an organization still wearing the name it was given
 *  automatically — "Priya's Organization" — which is what prints on every
 *  certificate and every verify page until someone changes it.
 *
 *  The name is edited in Clerk (see branding-card.tsx: two places to rename an
 *  org is how they get out of step), and the Clerk webhook carries it back to
 *  the API. Clerk's organization profile edits the *active* organization, so
 *  the prompt only appears when that is the org on screen; otherwise "Rename"
 *  would open some other organization's settings.
 */
export function RenamePrompt({ slug, name }: { slug: string; name: string }) {
  const clerk = useClerk();
  const { organization } = useOrganization();
  const stored = useSyncExternalStore(noSubscription, () => readDismissed(slug), () => true);
  const [dismissed, setDismissed] = useState(false);

  if (!looksAutoNamed(name) || stored || dismissed || organization?.slug !== slug) return null;

  return (
    <span className="ml-2 inline-flex items-center gap-1 rounded-full border border-accent-line bg-accent-wash py-0.5 pl-2.5 pr-1 align-middle text-xs text-accent">
      <button
        type="button"
        onClick={() => clerk.openOrganizationProfile()}
        className="font-medium underline-offset-2 hover:underline"
      >
        Rename your organization
      </button>
      <button
        type="button"
        aria-label="Dismiss rename suggestion"
        onClick={() => {
          writeDismissed(slug);
          setDismissed(true);
        }}
        className="flex h-5 w-5 items-center justify-center rounded-full hover:bg-accent-line"
      >
        <span aria-hidden>×</span>
      </button>
    </span>
  );
}

const noSubscription = () => () => {};
const key = (slug: string) => `certforge:rename-prompt-dismissed:${slug}`;

function readDismissed(slug: string): boolean {
  try {
    return window.localStorage.getItem(key(slug)) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(slug: string): void {
  try {
    window.localStorage.setItem(key(slug), "1");
  } catch {
    // Dismissed for this visit only.
  }
}
