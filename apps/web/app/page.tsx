import type { Metadata } from "next";

import { AccountPanel } from "@/components/account-panel";
import { VerifyLookup } from "@/components/verify-lookup";

export const metadata: Metadata = {
  title: { absolute: "CertForge — verifiable credentials" },
  description:
    "Issue tamper-evident certificates in bulk, let recipients claim them into a public passport, and let anyone verify one from its ID.",
};

const CAPABILITIES = [
  {
    title: "Bulk issuance",
    body: "Upload a CSV against a template and CertForge mints a signed credential per row, then reports the batch result.",
  },
  {
    title: "Recipient passports",
    body: "Recipients claim a credential into a passport page they own — one public URL for everything they have earned.",
  },
  {
    title: "Public verification",
    body: "Every credential resolves to a verification page and an Open Badges 3.0 document that anyone can check.",
  },
  {
    title: "API keys and webhooks",
    body: "Issue programmatically and get notified when a batch finishes, without polling.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-100 selection:bg-indigo-500/30">
      <div className="pointer-events-none fixed left-1/2 top-0 h-[420px] w-[820px] -translate-x-1/2 rounded-full bg-indigo-500/10 blur-[130px]" />

      <div className="relative mx-auto w-full max-w-5xl px-6">
        <header className="flex items-center justify-between py-8">
          <span className="text-lg font-semibold tracking-tight text-white">CertForge</span>
          <span className="text-sm text-zinc-500">by IntelliForge</span>
        </header>

        <main className="pb-24">
          <section className="py-16">
            <h1 className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight text-white md:text-5xl">
              Credentials your recipients keep, and anyone can verify.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-zinc-400">
              CertForge issues tamper-evident certificates for cohorts, internships and events.
              Recipients claim them into a passport of their own; verifiers check them from the
              credential ID alone.
            </p>
            <div className="mt-10">
              <AccountPanel />
            </div>
          </section>

          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-8">
            <h2 className="text-lg font-medium text-white">Verify a credential</h2>
            <p className="mb-6 mt-1 text-sm text-zinc-400">
              Paste the ID printed on a certificate or encoded in its QR code.
            </p>
            <VerifyLookup />
          </section>

          <section className="mt-16">
            <h2 className="text-lg font-medium text-white">What you get</h2>
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {CAPABILITIES.map((capability) => (
                <div
                  key={capability.title}
                  className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6"
                >
                  <h3 className="font-medium text-zinc-100">{capability.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-400">{capability.body}</p>
                </div>
              ))}
            </div>
          </section>
        </main>

        <footer className="border-t border-zinc-900 py-8 text-sm text-zinc-600">
          CertForge is in active development. Features not listed above are not available yet.
        </footer>
      </div>
    </div>
  );
}
