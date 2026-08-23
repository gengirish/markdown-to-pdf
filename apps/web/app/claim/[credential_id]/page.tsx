"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { SignInButton, useAuth } from "@clerk/nextjs";

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

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-zinc-950 px-6 text-white selection:bg-indigo-500/30">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-indigo-900/20 via-zinc-950 to-zinc-950" />

      <div className="z-10 w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 text-center shadow-2xl backdrop-blur-xl">
        {state.phase === "loading" || !isLoaded ? (
          <div className="space-y-6">
            <div className="mx-auto h-16 w-16 animate-spin rounded-full border-t-2 border-indigo-500" />
            <p className="text-zinc-400">Looking up this credential…</p>
          </div>
        ) : state.phase === "unavailable" ? (
          <div className="space-y-5">
            <IconBubble tone="red">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </IconBubble>
            <h1 className="text-2xl text-zinc-100">Credential unavailable</h1>
            <p className="text-zinc-400">{state.message}</p>
            <p className="font-mono text-xs text-zinc-600">{credentialId}</p>
          </div>
        ) : state.phase === "claimed" ? (
          <div className="space-y-6">
            <IconBubble tone="emerald">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </IconBubble>
            <h1 className="text-3xl font-light text-zinc-100">Added to your passport</h1>
            <p className="text-zinc-400">
              “{state.credential.title}” is now linked to your CertForge passport.
            </p>
            <Link
              href={`/passport/${state.username}`}
              className="block w-full rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 font-medium text-white transition-colors hover:bg-zinc-700"
            >
              View my passport
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            <IconBubble tone="indigo">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </IconBubble>

            <div className="space-y-1">
              <h1 className="text-2xl font-light tracking-tight text-zinc-100">
                {state.credential.title}
              </h1>
              <p className="text-zinc-400">Issued to {state.credential.name}</p>
              <p className="font-mono text-xs text-zinc-600">{state.credential.id}</p>
            </div>

            {state.phase === "failed" ? (
              <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {state.message}
              </p>
            ) : null}

            {isSignedIn ? (
              <button
                onClick={claim}
                disabled={state.phase === "claiming"}
                className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
              >
                {state.phase === "claiming" ? "Claiming…" : "Add to my passport"}
              </button>
            ) : (
              <>
                <p className="text-sm text-zinc-400">
                  Sign in to add this credential to your permanent CertForge passport.
                </p>
                <SignInButton mode="modal">
                  <button className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition-colors hover:bg-indigo-500">
                    Sign in to claim
                  </button>
                </SignInButton>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function IconBubble({
  tone,
  children,
}: {
  tone: "indigo" | "emerald" | "red";
  children: React.ReactNode;
}) {
  const tones = {
    indigo: "bg-indigo-500/10 text-indigo-400",
    emerald: "bg-emerald-500/10 text-emerald-400",
    red: "bg-red-500/10 text-red-400",
  } as const;

  return (
    <div className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full ${tones[tone]}`}>
      <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        {children}
      </svg>
    </div>
  );
}
