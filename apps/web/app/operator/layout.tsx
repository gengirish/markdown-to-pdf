import type { ReactNode } from "react";

// The page is a client component, so its metadata lives here. Staff-only:
// keep it out of search results even though the API is what guards it.
export const metadata = { title: "Operator", robots: { index: false, follow: false } };

export default function OperatorLayout({ children }: { children: ReactNode }) {
  return children;
}
