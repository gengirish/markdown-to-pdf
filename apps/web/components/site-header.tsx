import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";

/** The redesign's sticky masthead, shared by every public page.
 *
 *  Translucent over a blurred ground, so content scrolling under it stays
 *  legible without the header needing a hard edge.
 */
export function SiteHeader({ children }: { children?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-50 border-b border-hair bg-ground/90 backdrop-blur-xl">
      <div className="mx-auto flex h-[66px] max-w-[1200px] items-center gap-10 px-6 sm:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 no-underline">
          {/* text-ground, not text-white: the accent lightens in dark mode,
           *  where white on it measures 2.42:1. ground inverts with the
           *  theme and passes on both. */}
          <span className="flex h-[22px] w-[22px] items-center justify-center rounded-md bg-accent text-xs font-bold text-ground">
            C
          </span>
          <span className="font-display text-[19px] font-semibold tracking-[-0.02em] text-ink">
            CertForge
          </span>
        </Link>
        {children}
        <ThemeToggle className="ml-auto" />
      </div>
    </header>
  );
}
