"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUser, SignInButton } from "@clerk/nextjs";

export default function ClaimCredentialPage({ params }: { params: { credential_id: string } }) {
  const { isSignedIn, user, isLoaded } = useUser();
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "claiming" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [passportUsername, setPassportUsername] = useState("");

  useEffect(() => {
    if (isLoaded && isSignedIn) {
      handleClaim();
    } else if (isLoaded && !isSignedIn) {
      setStatus("error");
    }
  }, [isLoaded, isSignedIn]);

  const handleClaim = async () => {
    setStatus("claiming");
    try {
      // In a real implementation this would call the API:
      // const res = await fetch(`/api/v1/claims/${params.credential_id}`, { method: 'POST', headers: { Authorization: `Bearer ${await getToken()}` }});
      
      // Simulating network delay
      await new Promise(r => setTimeout(r, 1500));
      
      // Mock success for Phase 2 demo
      setPassportUsername(user?.firstName?.toLowerCase() || "user");
      setStatus("success");
    } catch (err: any) {
      setStatus("error");
      setErrorMsg(err.message || "Failed to claim credential");
    }
  };

  if (!isLoaded) return <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-white">Loading...</div>;

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-white selection:bg-indigo-500/30">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-indigo-900/20 via-zinc-950 to-zinc-950 pointer-events-none" />
      
      <div className="z-10 max-w-md w-full mx-auto p-8 rounded-2xl bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 shadow-2xl text-center transition-all">
        {status === "error" && !isSignedIn && (
          <div className="space-y-6 animate-in fade-in zoom-in duration-500">
            <div className="w-16 h-16 bg-indigo-500/10 rounded-full flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h1 className="text-3xl font-light tracking-tight text-zinc-100">Claim your Credential</h1>
            <p className="text-zinc-400">Sign in to add this credential to your permanent CertForge Passport.</p>
            <SignInButton mode="modal">
              <button className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition-colors">
                Sign in to Claim
              </button>
            </SignInButton>
          </div>
        )}

        {status === "claiming" && (
          <div className="space-y-6 animate-pulse">
            <div className="w-16 h-16 border-t-2 border-indigo-500 rounded-full animate-spin mx-auto" />
            <h1 className="text-2xl text-zinc-200">Verifying and claiming...</h1>
            <p className="text-zinc-500">Adding to your passport securely.</p>
          </div>
        )}

        {status === "success" && (
          <div className="space-y-6 animate-in fade-in zoom-in duration-500">
            <div className="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-3xl font-light text-zinc-100">Claimed Successfully!</h1>
            <p className="text-zinc-400">This credential is now permanently linked to your Passport.</p>
            <button 
              onClick={() => router.push(`/passport/${passportUsername}`)}
              className="w-full py-3 px-4 bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700 rounded-lg font-medium transition-colors"
            >
              View My Passport
            </button>
          </div>
        )}

        {status === "error" && isSignedIn && (
          <div className="space-y-6">
            <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl text-zinc-100">Error Claiming</h1>
            <p className="text-red-400">{errorMsg}</p>
          </div>
        )}
      </div>
    </div>
  );
}
