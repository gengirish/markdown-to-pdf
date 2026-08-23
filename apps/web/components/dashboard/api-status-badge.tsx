"use client";

import { useEffect, useState } from "react";

import { publicApi, type HealthStatus } from "@/lib/api";

/** Reflects a real `/api/health` probe — never a hardcoded "operational". */
export function ApiStatusBadge() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    publicApi
      .health(controller.signal)
      .then(setHealth)
      .catch(() => {
        if (!controller.signal.aborted) setUnreachable(true);
      });
    return () => controller.abort();
  }, []);

  const label = unreachable
    ? "API unreachable"
    : health === null
      ? "Checking API…"
      : health.dependencies?.database === "connected"
        ? "API operational"
        : "API up, database not configured";

  const dot = unreachable
    ? "bg-red-500"
    : health === null
      ? "bg-zinc-500"
      : health.dependencies?.database === "connected"
        ? "bg-emerald-500"
        : "bg-amber-500";

  return (
    <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      <span className="text-sm font-medium text-zinc-300">{label}</span>
    </div>
  );
}
