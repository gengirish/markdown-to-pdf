"use client";

import { useState } from "react";

import { publicApi } from "@/lib/api";
import { Eyebrow } from "@/components/dashboard/ui";

/** The real credential ID shape: `CF-` + a four-digit year + eight Crockford
 *  base32 characters, which excludes 0, 1, I, O and L so an ID read off paper
 *  cannot be mistyped into a different one.
 *
 *  Kept loose on purpose — it only decides whether to warn, never whether to
 *  submit. The API is the authority on whether an ID exists, and a client-side
 *  rule that refuses to send is a rule that will one day refuse a credential we
 *  really issued. (The redesign's mock used `CF-2026-8F3A-QK19` with an inner
 *  dash, which no CertForge ID has ever had.) */
const CREDENTIAL_ID = /^CF-\d{4}-[23456789ABCDEFGHJKMNPQRSTVWXYZ]{8}$/i;

/**
 * Sends a credential ID to the public verification page.
 *
 * That page is rendered by the API host, not this app, so this navigates away
 * rather than rendering the result here.
 */
export function VerifyLookup({ compact = false }: { compact?: boolean }) {
  const [credentialId, setCredentialId] = useState("");
  const trimmed = credentialId.trim();
  const misshapen = trimmed.length > 0 && !CREDENTIAL_ID.test(trimmed);

  return (
    <div>
      {compact ? (
        <div className="mb-3.5 flex items-center justify-between gap-3">
          <Eyebrow>Verify a credential</Eyebrow>
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
            Live now
          </span>
        </div>
      ) : null}

      <form
        className="flex flex-col gap-2.5 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!trimmed) return;
          window.location.href = publicApi.verificationPageUrl(trimmed);
        }}
      >
        <label htmlFor="credential-id" className="sr-only">
          Credential ID
        </label>
        <input
          id="credential-id"
          value={credentialId}
          onChange={(event) => setCredentialId(event.target.value)}
          placeholder="CF-2026-K7M2P9QX"
          autoComplete="off"
          spellCheck={false}
          aria-describedby={misshapen ? "credential-id-hint" : undefined}
          className="w-full min-w-0 flex-1 rounded-lg border border-hair bg-sunken px-3.5 py-3 font-mono text-sm tracking-[0.03em] text-ink focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={!trimmed}
          className="shrink-0 rounded-lg bg-ink px-5 py-3 text-sm font-medium text-ground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
        >
          Verify
        </button>
      </form>

      <p
        id="credential-id-hint"
        className="mt-2.5 text-xs leading-relaxed text-faint"
        aria-live="polite"
      >
        {misshapen
          ? "That does not look like a CertForge ID — they read CF-2026-K7M2P9QX. Sending it anyway will simply come back not found."
          : "Printed on the certificate and encoded in its QR code."}
      </p>
    </div>
  );
}
