"use client";

import { useEffect, useState } from "react";
import Image from "next/image";

// Mock data for Phase 2 demo
const MOCK_DATA = {
  profile: {
    username: "alice-dev",
    display_name: "Alice Engineer",
    bio: "Software developer passionate about scalable web architectures and lifelong learning."
  },
  credentials: [
    {
      id: "CF-2026-ABCDEF",
      title: "Python Web Development Bootcamp",
      recipient_name: "Alice Engineer",
      issued_at: "2026-06-15T10:00:00Z",
      pinned: true,
      metadata: { issuer: "IntelliForge Learning" }
    },
    {
      id: "CF-2026-987654",
      title: "Advanced System Design Certification",
      recipient_name: "Alice Engineer",
      issued_at: "2026-07-20T14:30:00Z",
      pinned: false,
      metadata: { issuer: "Hackathon XYZ" }
    }
  ]
};

export default function PassportPage({ params }: { params: { username: string } }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In real app, fetch from `/api/v1/passports/${params.username}`
    // For demo, we use mock data after a short delay
    setTimeout(() => {
      setData(MOCK_DATA);
      setLoading(false);
    }, 800);
  }, [params.username]);

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#0a0a0a] text-zinc-400">
        <div className="w-8 h-8 border-t-2 border-indigo-500 rounded-full animate-spin mb-4" />
        Loading passport...
      </div>
    );
  }

  if (!data) return <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] text-red-400">Passport not found</div>;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white selection:bg-indigo-500/30 font-sans pb-24">
      {/* Dynamic Background */}
      <div className="fixed inset-0 bg-[url('/noise.png')] opacity-[0.03] pointer-events-none" />
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-indigo-500/10 blur-[120px] rounded-full pointer-events-none" />
      
      {/* Header Profile Section */}
      <header className="relative pt-24 pb-16 px-6 max-w-5xl mx-auto flex flex-col items-center text-center">
        <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 p-[2px] mb-6 shadow-2xl shadow-indigo-500/20">
          <div className="w-full h-full rounded-full bg-zinc-900 border-4 border-[#0a0a0a] flex items-center justify-center text-2xl font-bold text-white">
            {data.profile.display_name.charAt(0)}
          </div>
        </div>
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-white to-white/70 mb-3">
          {data.profile.display_name}
        </h1>
        <p className="text-zinc-400 max-w-md mx-auto leading-relaxed">
          {data.profile.bio}
        </p>
      </header>

      {/* Masonry Credential Grid */}
      <main className="relative px-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-xl font-medium text-white/90">Verified Credentials</h2>
          <span className="text-sm font-medium text-indigo-400 bg-indigo-400/10 px-3 py-1 rounded-full">
            {data.credentials.length} Earned
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data.credentials.map((cred: any, i: number) => (
            <div 
              key={cred.id}
              className="group relative bg-zinc-900/40 backdrop-blur-md border border-zinc-800 hover:border-indigo-500/50 rounded-2xl p-6 transition-all duration-300 hover:shadow-2xl hover:shadow-indigo-500/10 hover:-translate-y-1 overflow-hidden"
            >
              {cred.pinned && (
                <div className="absolute top-4 right-4 text-amber-400">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M5 4a2 2 0 012-2h6a2 2 0 012 2v14l-5-2.5L5 18V4z" />
                  </svg>
                </div>
              )}
              
              <div className="mb-4">
                <span className="text-xs font-mono text-zinc-500 uppercase tracking-wider">{cred.metadata.issuer}</span>
                <h3 className="text-lg font-semibold text-zinc-100 mt-1 leading-tight group-hover:text-indigo-300 transition-colors">
                  {cred.title}
                </h3>
              </div>
              
              <div className="mt-8 flex items-center justify-between text-sm text-zinc-400">
                <span>{new Date(cred.issued_at).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span>
                <a 
                  href={`/verify/${cred.id}`} 
                  target="_blank" 
                  className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  Verify
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
