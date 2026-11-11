"use client";

import { useCallback, useEffect, useState } from "react";

import {
  resolveApiBaseUrl,
  toApiError,
  type ApiKeySummary,
  type CreatedApiKey,
  type CreatedWebhook,
  type WebhookDelivery,
  type WebhookSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import {
  WEBHOOK_COPY,
  deliveryStatusLabel,
  deliveryTagText,
  isRedeliverable,
  lastDeliveryOf,
  nextTryHint,
  redeliverErrorMessage,
} from "@/lib/webhook-deliveries";
import { ApiStatusBadge } from "./api-status-badge";
import {
  Card,
  EmptyNote,
  ErrorNote,
  Mono,
  Skeleton,
  StatusTag,
  buttonClass,
  formatDate,
} from "./ui";

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

      <p className="text-sm text-muted">{WEBHOOK_COPY.purpose}</p>

      {webhooks === null ? (
        <Skeleton rows={1} />
      ) : webhooks.length === 0 ? (
        !error ? (
          <div className="space-y-2">
            <EmptyNote>{WEBHOOK_COPY.empty}</EmptyNote>
            <p className="text-sm text-muted">
              Registering and removing endpoints over the API is in the <DocsLink />.
            </p>
          </div>
        ) : null
      ) : (
        webhooks.map((webhook) => (
          <WebhookRow
            key={webhook.id}
            slug={slug}
            webhook={webhook}
            busy={busy}
            onRemove={() => remove(webhook.id)}
            onChanged={() => load()}
          />
        ))
      )}
    </Panel>
  );
}

function DeliveryTag({ delivery }: { delivery: WebhookDelivery | null }) {
  if (!delivery) return <StatusTag tone="neutral">{WEBHOOK_COPY.noDeliveries}</StatusTag>;
  return <StatusTag tone={deliveryStatusLabel(delivery.status).tone}>{deliveryTagText(delivery)}</StatusTag>;
}

function NextTry({ at }: { at: string | null }) {
  const hint = nextTryHint(at);
  if (!hint) return null;
  return (
    <span title={WEBHOOK_COPY.lateRetryCaveat} className="cursor-help underline decoration-dotted underline-offset-2">
      {hint}
    </span>
  );
}

/** One endpoint: its last delivery as a tag, and its recent deliveries on demand.
 *  The list is fetched when opened, not with the card, so an org with many
 *  endpoints does not pay one request per endpoint on every dashboard load. */
function WebhookRow({
  slug,
  webhook,
  busy,
  onRemove,
  onChanged,
}: {
  slug: string;
  webhook: WebhookSummary;
  busy: boolean;
  onRemove: () => void;
  onChanged: () => void;
}) {
  const api = useCertForge();
  const last = lastDeliveryOf(webhook);
  const [open, setOpen] = useState(false);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState<Set<string>>(() => new Set());
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    api
      .listWebhookDeliveries(slug, webhook.id, controller.signal)
      .then((result) => {
        setDeliveries(result);
        setListError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setDeliveries([]);
        setListError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, open, slug, webhook.id]);

  const redeliver = useCallback(
    async (deliveryId: string) => {
      setInFlight((current) => new Set(current).add(deliveryId));
      setRowErrors((current) => {
        const next = { ...current };
        delete next[deliveryId];
        return next;
      });
      try {
        const updated = await api.redeliverWebhookDelivery(slug, webhook.id, deliveryId);
        setDeliveries((current) =>
          current ? current.map((row) => (row.id === updated.id ? updated : row)) : current,
        );
        onChanged();
      } catch (err) {
        setRowErrors((current) => ({ ...current, [deliveryId]: redeliverErrorMessage(toApiError(err)) }));
      } finally {
        setInFlight((current) => {
          const next = new Set(current);
          next.delete(deliveryId);
          return next;
        });
      }
    },
    [api, onChanged, slug, webhook.id],
  );

  const listId = `webhook-deliveries-${webhook.id}`;

  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{webhook.url}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-faint">
            <span>Events: {webhook.events.length > 0 ? webhook.events.join(", ") : "none"}</span>
            <DeliveryTag delivery={last} />
            {last ? <NextTry at={last.next_attempt_at} /> : null}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-4">
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-expanded={open}
            aria-controls={listId}
            className="text-accent underline-offset-2 hover:underline"
          >
            {open ? WEBHOOK_COPY.hideDeliveries : WEBHOOK_COPY.showDeliveries}
          </button>
          <button
            onClick={onRemove}
            disabled={busy}
            className="text-danger transition-colors hover:text-danger disabled:cursor-not-allowed disabled:text-muted"
          >
            Delete
          </button>
        </div>
      </div>

      {open ? (
        <div id={listId} className="rounded-lg border border-hair">
          {listError ? (
            <div className="p-3">
              <ErrorNote>{listError}</ErrorNote>
            </div>
          ) : deliveries === null ? (
            <div className="p-3">
              <Skeleton rows={2} />
            </div>
          ) : deliveries.length === 0 ? (
            <p className="p-3 text-muted">{WEBHOOK_COPY.deliveriesEmpty}</p>
          ) : (
            <ul className="divide-y divide-hair">
              {deliveries.map((delivery) => {
                const sending = inFlight.has(delivery.id);
                const rowError = rowErrors[delivery.id];
                return (
                  <li key={delivery.id} className="space-y-2 px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                        <DeliveryTag delivery={delivery} />
                        <Mono className="text-xs text-muted">{delivery.event}</Mono>
                        <span className="text-faint">
                          {formatDate(delivery.created_at)} · {delivery.attempts}{" "}
                          {delivery.attempts === 1 ? "attempt" : "attempts"}
                        </span>
                        <span className="text-faint">
                          <NextTry at={delivery.next_attempt_at} />
                        </span>
                      </div>
                      {isRedeliverable(delivery.status) ? (
                        <button
                          type="button"
                          onClick={() => redeliver(delivery.id)}
                          disabled={sending}
                          className={buttonClass("secondary", "sm")}
                        >
                          {sending ? WEBHOOK_COPY.redelivering : WEBHOOK_COPY.redeliver}
                        </button>
                      ) : null}
                    </div>
                    {delivery.last_error ? (
                      <p className="break-all font-mono text-xs text-muted">{delivery.last_error}</p>
                    ) : null}
                    {rowError ? <ErrorNote>{rowError}</ErrorNote> : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
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
