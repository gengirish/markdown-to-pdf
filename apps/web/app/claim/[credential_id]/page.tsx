"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { SignInButton, useAuth } from "@clerk/nextjs";

import { SiteHeader } from "@/components/site-header";
import { Eyebrow, ErrorNote, Mono, buttonClass } from "@/components/dashboard/ui";
import { publicApi, toApiError, type VerifiedCredential } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";

type ClaimState =
  | { phase: "loading" }
  | { phase: "unavailable"; message: string }
  | { phase: "ready"; credential: VerifiedCredential }
  | { phase: "claiming"; credential: VerifiedCredential }
  | { phase: "claimed"; credential: VerifiedCredential; username: string }
  | { phase: "failed"; credential: VerifiedCredential; message: string };

export default function ClaimCredentialPage({
  params,
}: {
  params: Promise<{ credential_id: string }>;
}) {
  const { credential_id: credentialId } = use(params);
  const { isLoaded, isSignedIn } = useAuth();
  const api = useCertForge();
  const [state, setState] = useState<ClaimState>({ phase: "loading" });
  const [copied, setCopied] = useState(false);

  // Show what is actually being claimed before asking for a signature. The
  // public verify endpoint is the only read of a single credential that exists.
  useEffect(() => {
    const controller = new AbortController();
    publicApi
      .verifyCredential(credentialId, controller.signal)
      .then((credential) => setState({ phase: "ready", credential }))
      .catch((err) => {
        if (controller.signal.aborted) return;
        const error = toApiError(err);
        setState({
          phase: "unavailable",
          message: error.isNotFound
            ? "This credential does not exist, has been revoked, or the link is incomplete."
            : error.message,
        });
      });
    return () => controller.abort();
  }, [credentialId]);

  const claim = useCallback(async () => {
    setState((current) =>
      current.phase === "ready" || current.phase === "failed"
        ? { phase: "claiming", credential: current.credential }
        : current,
    );
    try {
      const result = await api.claimCredential(credentialId);
      setState((current) =>
        current.phase === "claiming"
          ? { phase: "claimed", credential: current.credential, username: result.username }
          : current,
      );
    } catch (err) {
      const error = toApiError(err);
      setState((current) =>
        current.phase === "claiming"
          ? {
              phase: "failed",
              credential: current.credential,
              message: error.isForbidden
                ? "This credential has already been claimed by someone else."
                : error.message,
            }
          : current,
      );
    }
  }, [api, credentialId]);

  const step = state.phase === "claimed" ? 2 : 1;

  return (
    <div className="min-h-screen bg-ground">
      <SiteHeader />

      <main className="mx-auto max-w-[620px] px-6 pb-24 pt-12 sm:px-8">
        {state.phase !== "unavailable" ? (
          <div className="mb-5">
            <Eyebrow>Claim · step {step} of 2</Eyebrow>
          </div>
        ) : null}

        <div className="overflow-hidden rounded-xl border border-hair bg-surface shadow-[var(--cf-shadow-card)]">
          <div
            className={`h-1 ${
              state.phase === "unavailable"
                ? "bg-danger"
                : state.phase === "claimed"
                  ? "bg-accent"
                  : "bg-hair"
            }`}
          />

          <div className="p-7 sm:p-8">
            {state.phase === "loading" || !isLoaded ? (
              <div className="space-y-4" aria-busy>
                <div className="h-7 w-2/3 animate-pulse rounded bg-well" />
                <div className="h-24 animate-pulse rounded-lg bg-well" />
                <p className="text-sm text-muted">Looking up this credential…</p>
              </div>
            ) : state.phase === "unavailable" ? (
              <div>
                <h1 className="mb-2.5 font-display text-[26px] font-semibold tracking-[-0.025em] text-ink">
                  Credential unavailable
                </h1>
                <p className="mb-4 text-sm leading-relaxed text-muted">{state.message}</p>
                <Mono className="text-xs text-faint">{credentialId}</Mono>
                <div className="mt-6">
                  <Link href="/" className={`${buttonClass("secondary")} no-underline`}>
                    Back to CertForge
                  </Link>
                </div>
              </div>
            ) : state.phase === "claimed" ? (
              <div>
                <span
                  aria-hidden
                  className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-accent-line bg-accent-wash text-xl text-accent"
                >
                  ✓
                </span>
                <h1 className="mb-2.5 font-display text-[30px] font-semibold tracking-[-0.03em] text-ink">
                  It&rsquo;s yours.
                </h1>
                <p className="mb-6 text-sm leading-relaxed text-muted">
                  “{state.credential.title}” now lives at a passport URL only you can change.
                  Nothing else to set up.
                </p>

                <div className="mb-6 rounded-lg border border-hair-soft bg-sunken p-4">
                  <div className="mb-2">
                    <Eyebrow>Your passport</Eyebrow>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <Mono className="text-sm text-ink">/passport/{state.username}</Mono>
                    <button
                      type="button"
                      onClick={() => {
                        void navigator.clipboard
                          ?.writeText(`${window.location.origin}/passport/${state.username}`)
                          .then(() => {
                            setCopied(true);
                            setTimeout(() => setCopied(false), 2000);
                          });
                      }}
                      className="text-xs text-accent hover:underline"
                    >
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>

                <Link
                  href={`/passport/${state.username}`}
                  className={`${buttonClass("primary")} no-underline`}
                >
                  Open my passport
                </Link>
              </div>
            ) : (
              <div>
                <h1 className="mb-2.5 font-display text-[26px] font-semibold leading-tight tracking-[-0.025em] text-ink">
                  {state.credential.issuer?.name
                    ? `${state.credential.issuer.name} issued you a credential.`
                    : "You have been issued a credential."}
                </h1>
                <p className="mb-6 text-sm leading-relaxed text-muted">
                  It already verifies publicly. Claiming it just puts it in a passport you control —
                  and it never changes whether the credential is valid.
                </p>

                <div className="mb-6 rounded-lg border border-hair-soft bg-sunken p-5">
                  <div className="text-[15px] font-medium leading-snug text-ink">
                    {state.credential.title}
                  </div>
                  <div className="mt-3 h-px bg-hair-soft" />
                  <div className="mt-3 text-sm text-muted">
                    Awarded to <strong className="font-medium text-ink">{state.credential.name}</strong>
                  </div>
                  <Mono className="mt-1.5 block text-xs text-faint">{state.credential.id}</Mono>
                </div>

                {state.phase === "failed" ? (
                  <div className="mb-5">
                    <ErrorNote>{state.message}</ErrorNote>
                  </div>
                ) : null}

                {isSignedIn ? (
                  <button
                    onClick={claim}
                    disabled={state.phase === "claiming"}
                    className={buttonClass("primary")}
                  >
                    {state.phase === "claiming" ? "Claiming…" : "Claim into my passport"}
                  </button>
                ) : (
                  <>
                    <SignInButton mode="modal">
                      <button className={buttonClass("primary")}>Sign in to claim</button>
                    </SignInButton>
                    <p className="mt-3.5 text-xs leading-relaxed text-faint">
                      Signing in is how the passport knows it is yours.{" "}
                      <a
                        href={publicApi.verificationPageUrl(credentialId)}
                        className="text-accent no-underline hover:underline"
                      >
                        Not you? See who this belongs to
                      </a>
                    </p>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
