import type { Metadata } from "next";
import Link from "next/link";

import { publicApi, toApiError, type PassportView } from "@/lib/api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ username: string }>;
}): Promise<Metadata> {
  const { username } = await params;
  return {
    title: `@${username}`,
    description: `Verified credentials earned by @${username}.`,
  };
}

/**
 * A recipient's public credential passport.
 *
 * Rendered on the server: the page is public, has no session to read, and is
 * something we want search engines and link previews to see. The route has no
 * `generateStaticParams`, so it is server-rendered on demand and never fetches
 * at build time.
 */
export default async function PassportPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;

  let passport: PassportView;
  try {
    passport = await publicApi.getPassport(username);
  } catch (err) {
    const error = toApiError(err);
    return (
      <PassportShell>
        <div className="mx-6 mt-32 max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 text-center sm:mx-auto">
          <h1 className="text-2xl font-medium text-zinc-100">
            {error.isNotFound
              ? "No passport here"
              : error.isForbidden
                ? "This passport is private"
                : "Passport unavailable"}
          </h1>
          <p className="mt-3 text-zinc-400">
            {error.isNotFound
              ? `Nobody has claimed the passport “${username}” yet.`
              : error.message}
          </p>
          <Link
            href="/"
            className="mt-6 inline-block rounded-lg border border-zinc-700 px-5 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-800"
          >
            Back to CertForge
          </Link>
        </div>
      </PassportShell>
    );
  }

  const { profile, credentials } = passport;
  const displayName = profile.display_name?.trim() || profile.username;

  return (
    <PassportShell>
      <header className="mx-auto flex max-w-5xl flex-col items-center px-6 pb-16 pt-24 text-center">
        <div className="mb-6 h-24 w-24 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 p-[2px] shadow-2xl shadow-indigo-500/20">
          <div className="flex h-full w-full items-center justify-center rounded-full border-4 border-[#0a0a0a] bg-zinc-900 text-2xl font-bold text-white">
            {displayName.charAt(0).toUpperCase()}
          </div>
        </div>
        <h1 className="mb-3 bg-gradient-to-b from-white to-white/70 bg-clip-text text-4xl font-semibold tracking-tight text-transparent md:text-5xl">
          {displayName}
        </h1>
        <p className="font-mono text-sm text-zinc-500">@{profile.username}</p>
        {profile.bio ? (
          <p className="mx-auto mt-4 max-w-md leading-relaxed text-zinc-400">{profile.bio}</p>
        ) : null}
      </header>

      <main className="mx-auto max-w-5xl px-6">
        <div className="mb-8 flex items-center justify-between">
          <h2 className="text-xl font-medium text-white/90">Verified credentials</h2>
          <span className="rounded-full bg-indigo-400/10 px-3 py-1 text-sm font-medium text-indigo-400">
            {credentials.length} earned
          </span>
        </div>

        {credentials.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-800 p-12 text-center">
            <p className="text-zinc-300">No credentials claimed yet.</p>
            <p className="mt-2 text-sm text-zinc-500">
              Credentials appear here once they are claimed from an issuer&apos;s invitation link.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {credentials.map((credential) => {
              const issuer = credential.metadata?.issuer;
              return (
                <div
                  key={credential.id}
                  className="group relative overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/50 hover:shadow-2xl hover:shadow-indigo-500/10"
                >
                  {credential.pinned ? (
                    <div className="absolute right-4 top-4 text-amber-400" title="Pinned">
                      <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M5 4a2 2 0 012-2h6a2 2 0 012 2v14l-5-2.5L5 18V4z" />
                      </svg>
                    </div>
                  ) : null}

                  <div className="mb-4">
                    {typeof issuer === "string" && issuer ? (
                      <span className="font-mono text-xs uppercase tracking-wider text-zinc-500">
                        {issuer}
                      </span>
                    ) : null}
                    <h3 className="mt-1 text-lg font-semibold leading-tight text-zinc-100 transition-colors group-hover:text-indigo-300">
                      {credential.title}
                    </h3>
                  </div>

                  <div className="mt-8 flex items-center justify-between text-sm text-zinc-400">
                    <span>{formatIssueDate(credential.issued_at)}</span>
                    <a
                      href={publicApi.verificationPageUrl(credential.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-indigo-400 transition-colors hover:text-indigo-300"
                    >
                      Verify
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        />
                      </svg>
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </PassportShell>
  );
}

function PassportShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#0a0a0a] pb-24 font-sans text-white selection:bg-indigo-500/30">
      <div className="pointer-events-none fixed left-1/2 top-0 h-[400px] w-[800px] -translate-x-1/2 rounded-full bg-indigo-500/10 blur-[120px]" />
      <div className="relative">{children}</div>
    </div>
  );
}

function formatIssueDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
