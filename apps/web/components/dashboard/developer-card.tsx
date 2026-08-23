"use client";

import { useCallback, useEffect, useState } from "react";

import {
  toApiError,
  type ApiKeySummary,
  type CreatedApiKey,
  type CreatedWebhook,
  type WebhookSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { Card, EmptyNote, ErrorNote, Skeleton, formatDate } from "./ui";

export function DeveloperCard({ slug }: { slug: string }) {
  return (
    <Card
      title="Developer settings"
      description="API keys and webhook endpoints for issuing programmatically."
    >
      <div className="space-y-6">
        <ApiKeysPanel slug={slug} />
        <WebhooksPanel slug={slug} />
      </div>
    </Card>
  );
}

function Panel({
  title,
  action,
  children,
}: {
  title: string;
  action: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      <div className="flex items-center justify-between gap-4 border-b border-zinc-800 bg-zinc-800/50 px-4 py-3">
        <h3 className="font-medium text-zinc-200">{title}</h3>
        {action}
      </div>
      <div className="space-y-4 p-4">{children}</div>
    </div>
  );
}

function ApiKeysPanel({ slug }: { slug: string }) {
  const api = useCertForge();
  const [keys, setKeys] = useState<ApiKeySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) =>
      api
        .listApiKeys(slug, signal)
        .then((result) => {
          setKeys(result);
          setError(null);
        })
        .catch((err) => {
          if (signal?.aborted) return;
          setKeys([]);
          setError(toApiError(err).message);
        }),
    [api, slug],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const generate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const key = await api.createApiKey(slug, `Key ${new Date().toISOString().slice(0, 10)}`);
      setCreated(key);
      await load();
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }, [api, load, slug]);

  const revoke = useCallback(
    async (keyId: string) => {
      setBusy(true);
      setError(null);
      try {
        await api.revokeApiKey(slug, keyId);
        await load();
      } catch (err) {
        setError(toApiError(err).message);
      } finally {
        setBusy(false);
      }
    },
    [api, load, slug],
  );

  return (
    <Panel
      title="API keys"
      action={
        <button
          onClick={generate}
          disabled={busy}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm text-white transition-colors hover:bg-indigo-500 disabled:bg-zinc-700 disabled:text-zinc-400"
        >
          Generate new key
        </button>
      }
    >
      {created ? (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
          <p className="text-sm font-medium text-amber-300">
            Copy this key now — it is never shown again.
          </p>
          <code className="mt-2 block break-all font-mono text-xs text-amber-100">
            {created.raw_key}
          </code>
          <button
            onClick={() => setCreated(null)}
            className="mt-3 text-xs text-amber-300/80 underline hover:text-amber-200"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {keys === null ? (
        <Skeleton rows={2} />
      ) : keys.length === 0 ? (
        !error ? <EmptyNote>No active API keys.</EmptyNote> : null
      ) : (
        keys.map((key) => (
          <div key={key.id} className="flex items-center justify-between gap-4 text-sm">
            <div>
              <p className="font-medium text-zinc-300">{key.label}</p>
              <p className="mt-1 text-zinc-500">
                Created {formatDate(key.created_at)} · Last used {formatDate(key.last_used_at)}
              </p>
            </div>
            <button
              onClick={() => revoke(key.id)}
              disabled={busy}
              className="text-red-400 transition-colors hover:text-red-300 disabled:text-zinc-600"
            >
              Revoke
            </button>
          </div>
        ))
      )}
    </Panel>
  );
}

function WebhooksPanel({ slug }: { slug: string }) {
  const api = useCertForge();
  const [webhooks, setWebhooks] = useState<WebhookSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");
  const [created, setCreated] = useState<CreatedWebhook | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) =>
      api
        .listWebhooks(slug, signal)
        .then((result) => {
          setWebhooks(result);
          setError(null);
        })
        .catch((err) => {
          if (signal?.aborted) return;
          setWebhooks([]);
          setError(toApiError(err).message);
        }),
    [api, slug],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const add = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const webhook = await api.createWebhook(slug, { url: trimmed });
      setCreated(webhook);
      setUrl("");
      setAdding(false);
      await load();
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }, [api, load, slug, url]);

  const remove = useCallback(
    async (webhookId: string) => {
      setBusy(true);
      setError(null);
      try {
        await api.deleteWebhook(slug, webhookId);
        await load();
      } catch (err) {
        setError(toApiError(err).message);
      } finally {
        setBusy(false);
      }
    },
    [api, load, slug],
  );

  return (
    <Panel
      title="Webhook endpoints"
      action={
        <button
          onClick={() => setAdding((current) => !current)}
          className="rounded-md bg-zinc-700 px-3 py-1.5 text-sm text-white transition-colors hover:bg-zinc-600"
        >
          {adding ? "Cancel" : "Add endpoint"}
        </button>
      }
    >
      {adding ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com/hooks/certforge"
            className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500/60 focus:outline-none"
          />
          <button
            onClick={add}
            disabled={busy || !url.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-500"
          >
            Save
          </button>
        </div>
      ) : null}

      {created ? (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
          <p className="text-sm font-medium text-amber-300">
            Signing secret — shown once. Store it before leaving this page.
          </p>
          <code className="mt-2 block break-all font-mono text-xs text-amber-100">
            {created.secret}
          </code>
          <button
            onClick={() => setCreated(null)}
            className="mt-3 text-xs text-amber-300/80 underline hover:text-amber-200"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {webhooks === null ? (
        <Skeleton rows={1} />
      ) : webhooks.length === 0 ? (
        !error ? <EmptyNote>No webhook endpoints registered.</EmptyNote> : null
      ) : (
        webhooks.map((webhook) => (
          <div key={webhook.id} className="flex items-center justify-between gap-4 text-sm">
            <div className="min-w-0">
              <p className="truncate font-medium text-zinc-300">{webhook.url}</p>
              <p className="mt-1 text-zinc-500">
                Events: {webhook.events.length > 0 ? webhook.events.join(", ") : "none"}
              </p>
            </div>
            <button
              onClick={() => remove(webhook.id)}
              disabled={busy}
              className="shrink-0 text-red-400 transition-colors hover:text-red-300 disabled:text-zinc-600"
            >
              Delete
            </button>
          </div>
        ))
      )}
    </Panel>
  );
}
