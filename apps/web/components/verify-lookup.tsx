"use client";

import { useState } from "react";

import { publicApi } from "@/lib/api";

/**
 * Sends a credential ID to the public verification page.
 *
 * That page is rendered by the API host, not this app, so this navigates away
 * rather than rendering the result here.
 */
export function VerifyLookup() {
  const [credentialId, setCredentialId] = useState("");
  const trimmed = credentialId.trim();

  return (
    <form
      className="flex flex-col gap-3 sm:flex-row"
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
        placeholder="CF-2026-XXXXXX"
        autoComplete="off"
        spellCheck={false}
        className="w-full flex-1 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 font-mono text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500/60 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!trimmed}
        className="rounded-lg border border-zinc-700 px-6 py-3 font-medium text-zinc-200 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Verify
      </button>
    </form>
  );
}
