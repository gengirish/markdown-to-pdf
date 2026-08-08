"use client";

import { useState } from "react";
import { useUser } from "@clerk/nextjs";

export default function OrgDashboard({ params }: { params: { slug: string } }) {
  const { user, isLoaded } = useUser();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setResult(null);

    try {
      // Mocked for Phase 2 demo
      await new Promise(r => setTimeout(r, 2000));
      setResult({ success: true, batchId: "b-12345", total: 150 });
    } catch (err) {
      setResult({ success: false, error: "Failed to upload CSV" });
    } finally {
      setUploading(false);
    }
  };

  if (!isLoaded) return <div className="min-h-screen bg-[#0a0a0a]" />;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-100 p-8 font-sans">
      <header className="max-w-6xl mx-auto mb-12 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-2">
            Credential Studio
          </h1>
          <p className="text-zinc-400">Manage issues and track analytics for {params.slug}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-sm font-medium text-zinc-300">API Operational</span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Actions */}
        <div className="lg:col-span-2 space-y-8">
          <div className="bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-8">
            <h2 className="text-xl font-medium text-white mb-6">Bulk Issue via CSV</h2>
            
            <div className="border-2 border-dashed border-zinc-800 hover:border-indigo-500/50 transition-colors rounded-xl p-12 text-center relative overflow-hidden group">
              <input 
                type="file" 
                accept=".csv"
                onChange={handleFileChange}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
              />
              <div className="w-16 h-16 bg-zinc-800/50 group-hover:bg-indigo-500/10 rounded-full flex items-center justify-center mx-auto mb-4 transition-colors">
                <svg className="w-8 h-8 text-zinc-400 group-hover:text-indigo-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-zinc-300 font-medium mb-1">
                {file ? file.name : "Click or drag CSV file here"}
              </p>
              <p className="text-sm text-zinc-500">
                Must include name, title, and email columns.
              </p>
            </div>

            <div className="mt-6 flex justify-end">
              <button 
                onClick={handleUpload}
                disabled={!file || uploading}
                className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-500 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {uploading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-zinc-400 border-t-white rounded-full animate-spin" />
                    Processing...
                  </>
                ) : (
                  "Start Issuance"
                )}
              </button>
            </div>

            {result && result.success && (
              <div className="mt-6 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-start gap-4">
                <svg className="w-6 h-6 text-emerald-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <h4 className="text-emerald-400 font-medium">Batch Started</h4>
                  <p className="text-sm text-emerald-400/80 mt-1">Successfully queued {result.total} credentials for processing. Batch ID: {result.batchId}</p>
                </div>
              </div>
            )}
          </div>
          </div>

          <div className="bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-8 mt-8">
            <h2 className="text-xl font-medium text-white mb-2">Developer Settings</h2>
            <p className="text-zinc-400 mb-6 text-sm">Manage your API keys and Webhook endpoints for programatic access.</p>
            
            <div className="space-y-6">
              {/* API Keys */}
              <div className="border border-zinc-800 rounded-xl overflow-hidden">
                <div className="bg-zinc-800/50 px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                  <h3 className="font-medium text-zinc-200">API Keys</h3>
                  <button className="text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-md transition-colors">
                    Generate New Key
                  </button>
                </div>
                <div className="p-4">
                  <div className="flex items-center justify-between text-sm">
                    <div>
                      <p className="font-medium text-zinc-300">Production Key 1</p>
                      <p className="text-zinc-500 font-mono mt-1">cf_prod_************************</p>
                    </div>
                    <div className="text-right">
                      <p className="text-zinc-500 mb-1">Created 2 days ago</p>
                      <button className="text-red-400 hover:text-red-300 transition-colors">Revoke</button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Webhooks */}
              <div className="border border-zinc-800 rounded-xl overflow-hidden">
                <div className="bg-zinc-800/50 px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                  <h3 className="font-medium text-zinc-200">Webhook Endpoints</h3>
                  <button className="text-sm bg-zinc-700 hover:bg-zinc-600 text-white px-3 py-1.5 rounded-md transition-colors">
                    Add Endpoint
                  </button>
                </div>
                <div className="p-4">
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                      <div>
                        <p className="font-medium text-zinc-300">https://api.example.com/webhooks/certforge</p>
                        <p className="text-zinc-500 mt-1">Events: batch.completed</p>
                      </div>
                    </div>
                    <button className="text-red-400 hover:text-red-300 transition-colors">Delete</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

        {/* Right Column: Usage & Stats */}
        <div className="space-y-8">
          <div className="bg-gradient-to-br from-indigo-900/40 to-purple-900/40 border border-indigo-500/20 rounded-2xl p-6 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/20 blur-3xl rounded-full" />
            <h3 className="text-sm font-medium text-indigo-300 uppercase tracking-wider mb-4">Monthly Usage</h3>
            <div className="flex items-baseline gap-2 mb-2">
              <span className="text-4xl font-bold text-white">1,240</span>
              <span className="text-zinc-400">/ 5,000</span>
            </div>
            <div className="w-full h-2 bg-black/40 rounded-full mt-4 overflow-hidden">
              <div className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 w-[25%]" />
            </div>
            <button className="mt-6 w-full py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm font-medium transition-colors backdrop-blur-md">
              Upgrade Plan
            </button>
          </div>

          <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6">
            <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-4">Recent Activity</h3>
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center">
                    <svg className="w-4 h-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-zinc-200">Batch Issued</p>
                    <p className="text-xs text-zinc-500">2 hours ago • 50 certs</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
