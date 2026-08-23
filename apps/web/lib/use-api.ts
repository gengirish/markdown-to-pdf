"use client";

import { useMemo } from "react";
import { useAuth } from "@clerk/nextjs";

import { CertForgeClient } from "./api";

/**
 * A `CertForgeClient` bound to the signed-in user's Clerk session.
 *
 * Clerk memoises `getToken` against the Clerk instance rather than the session,
 * so the client below is stable for the life of the component and is safe to
 * list in effect dependency arrays.
 */
export function useCertForge(): CertForgeClient {
  const { getToken } = useAuth();
  return useMemo(() => new CertForgeClient({ getToken }), [getToken]);
}
