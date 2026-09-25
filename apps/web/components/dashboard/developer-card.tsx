"use client";

import { useCallback, useEffect, useState } from "react";

import {
  resolveApiBaseUrl,
  toApiError,
  type ApiKeySummary,
  type CreatedApiKey,
  type CreatedWebhook,
  type WebhookSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { ApiStatusBadge } from "./api-status-badge";
import { Card, EmptyNote, ErrorNote, Skeleton, buttonClass, formatDate } from "./ui";

export function DeveloperCard({ slug }: { slug: string }) {
  return (
    <Card
      title="Developer settings"
      description="API keys and webhook endpoints for issuing programmatically."
      action={<ApiStatusBadge />}
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
    <div className="overflow-hidden rounded-xl border border-hair">
      <div className="flex items-center justify-between gap-4 border-b border-hair bg-well px-4 py-3">
        <h3 className="font-medium text-ink">{title}</h3>
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
          type="button"
          onClick={generate}
          disabled={busy}
          className={buttonClass("primary", "sm")}
        >
          Generate new key
        </button>
      }
    >
      {created ? (
        <div className="rounded-lg border border-warn-line bg-warn-wash p-4">
          <p className="text-sm font-medium text-warn-ink">
            Copy this key now — it is never shown again.
          </p>
          <code className="mt-2 block break-all font-mono text-xs text-warn-ink">
            {created.raw_key}
          </code>
          <button
            onClick={() => setCreated(null)}
            className="mt-3 text-xs text-warn-ink underline hover:text-warn-ink"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {created ? <Quickstart slug={slug} apiKey={created.raw_key} /> : null}

      {keys === null ? (
        <Skeleton rows={2} />
      ) : keys.length === 0 ? (
        !error ? (
          <>
            <EmptyNote>No active API keys. Generate one to issue from your own code.</EmptyNote>
            {created ? null : <Quickstart slug={slug} />}
          </>
        ) : null
      ) : (
        keys.map((key) => (
          <div key={key.id} className="flex items-center justify-between gap-4 text-sm">
            <div>
              <p className="font-medium text-ink">{key.label}</p>
              <p className="mt-1 text-faint">
                Created {formatDate(key.created_at)} · Last used {formatDate(key.last_used_at)}
              </p>
            </div>
            <button
              onClick={() => revoke(key.id)}
              disabled={busy}
              className="text-danger transition-colors hover:text-danger disabled:cursor-not-allowed disabled:text-muted"
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
          type="button"
          onClick={() => setAdding((current) => !current)}
          aria-expanded={adding}
          className={`${buttonClass("secondary", "sm")} bg-surface`}
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
            className="flex-1 rounded-lg border border-hair bg-surface px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
          />
          <button
            onClick={add}
            disabled={busy || !url.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ground transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-well disabled:text-muted disabled:hover:bg-well"
          >
            Save
          </button>
        </div>
      ) : null}

      {created ? (
        <div className="rounded-lg border border-warn-line bg-warn-wash p-4">
          <p className="text-sm font-medium text-warn-ink">
            Signing secret — shown once. Store it before leaving this page.
          </p>
          <code className="mt-2 block break-all font-mono text-xs text-warn-ink">
            {created.secret}
          </code>
          <button
            onClick={() => setCreated(null)}
            className="mt-3 text-xs text-warn-ink underline hover:text-warn-ink"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {webhooks === null ? (
        <Skeleton rows={1} />
      ) : webhooks.length === 0 ? (
        !error ? (
          <div className="space-y-2">
            <EmptyNote>
              No webhook endpoints registered. Add one to be told when a credential is issued.
            </EmptyNote>
            <p className="text-sm text-muted">
              Registering and removing endpoints over the API is in the <DocsLink />.
            </p>
          </div>
        ) : null
      ) : (
        webhooks.map((webhook) => (
          <div key={webhook.id} className="flex items-center justify-between gap-4 text-sm">
            <div className="min-w-0">
              <p className="truncate font-medium text-ink">{webhook.url}</p>
              <p className="mt-1 text-faint">
                Events: {webhook.events.length > 0 ? webhook.events.join(", ") : "none"}
              </p>
            </div>
            <button
              onClick={() => remove(webhook.id)}
              disabled={busy}
              className="shrink-0 text-danger transition-colors hover:text-danger disabled:cursor-not-allowed disabled:text-muted"
            >
              Delete
            </button>
          </div>
        ))
      )}
    </Panel>
  );
}

/** The API reference: FastAPI's interactive docs on the API host, which are
 *  generated from the routes themselves and so cannot describe an endpoint
 *  that does not exist. */
function DocsLink() {
  return (
    <a
      href={`${resolveApiBaseUrl()}/docs`}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-accent underline-offset-2 hover:underline"
    >
      API reference
    </a>
  );
}

/** A request that works as pasted: this org's slug, the real API host and,
 *  straight after a key is generated, that key. Before then the key is a
 *  visible placeholder rather than anything that looks like a real value. */
function Quickstart({ slug, apiKey }: { slug: string; apiKey?: string }) {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const command = [
    `curl -X POST ${resolveApiBaseUrl()}/api/v1/orgs/${slug}/credentials \\`,
    `  -H "Authorization: Bearer ${apiKey ?? "cf_live_YOUR_KEY"}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"recipient_name": "Ada Lovelace", "title": "Analytical Engines", "recipient_email": "ada@example.com", "send_email": true}'`,
  ].join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied("copied");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <div className="rounded-lg border border-hair">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hair px-3 py-2">
        <p className="text-sm font-medium text-ink">Issue a credential with one request</p>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted" aria-live="polite">
            {copied === "copied" ? "Copied" : copied === "failed" ? "Copy blocked by the browser" : ""}
          </span>
          <button type="button" onClick={copy} className={buttonClass("secondary", "sm")}>
            Copy
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto px-3 py-3 font-mono text-xs leading-relaxed text-ink">
        <code>{command}</code>
      </pre>
      <p className="border-t border-hair px-3 py-2 text-xs text-muted">
        Use a <span className="font-mono">cf_test_</span> key to try it without emailing anyone.
        Every field is in the <DocsLink />.
      </p>
    </div>
  );
}
