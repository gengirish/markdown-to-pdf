"use client";

/**
 * Last-resort boundary: an error thrown in the root layout replaces it
 * entirely, so this file provides its own `<html>` and `<body>`.
 *
 * DO NOT DELETE THIS AS UNUSED BOILERPLATE. It is load-bearing at build time,
 * not just at runtime. Without it, `next build` prerenders Next's built-in
 * /_global-error, which Clerk's keyless path routes through when no
 * publishable key is set, and the build dies with:
 *
 *     InvariantError: Expected workStore to be initialized
 *
 * Defining our own boundary replaces that built-in page, so the app builds
 * with no Clerk environment configured at all — which is what CI does.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a] px-6 text-zinc-100">
          <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 text-center">
            <h1 className="text-2xl font-medium text-white">Something broke</h1>
            <p className="mt-3 text-sm text-zinc-400">
              CertForge hit an unexpected error and could not render this page.
            </p>
            {error.digest ? (
              <p className="mt-4 font-mono text-xs text-zinc-600">Reference: {error.digest}</p>
            ) : null}
            <button
              onClick={reset}
              className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
