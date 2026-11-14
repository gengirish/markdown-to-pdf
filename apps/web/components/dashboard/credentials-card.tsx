"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  publicApi,
  toApiError,
  type CredentialListQuery,
  type CredentialSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { ResendFailedButton, describeQueued } from "./resend-failed";
import { EmptyNote, ErrorNote, Skeleton, StatusTag, buttonClass, formatDate, inputClass } from "./ui";

/** Every credential the org has issued: searchable, filterable, and each row
 *  something you can act on.
 *
 *  All searching and filtering is the API's (`GET /orgs/{slug}/credentials`
 *  with `q`, `status`, `delivery_status`, `template_id`, `test`). Filtering
 *  only the rows already loaded would print "3 results" beside a list that has
 *  a fourth on page two, and "N total" would describe a different list from
 *  the one on screen.
 */

const PAGE_SIZE = 25;

type StatusFilter = "all" | "issued" | "revoked" | "email_failed" | "email_scheduled";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "issued", label: "Issued" },
  { value: "revoked", label: "Revoked" },
  { value: "email_failed", label: "Email failed" },
  { value: "email_scheduled", label: "Email scheduled" },
];

interface Filters {
  q: string;
  status: StatusFilter;
  templateId: string;
  hideTest: boolean;
}

function toQuery(filters: Filters): CredentialListQuery {
  return {
    q: filters.q.trim() || undefined,
    status:
      filters.status === "issued" || filters.status === "revoked" ? filters.status : undefined,
    deliveryStatus:
      filters.status === "email_failed"
        ? "failed"
        : filters.status === "email_scheduled"
          ? "deferred"
          : undefined,
    templateId: filters.templateId || undefined,
    test: filters.hideTest ? "exclude" : undefined,
  };
}

export function CredentialsCard({
  slug,
  refreshToken,
}: {
  slug: string;
  /** Bumped by the issuance cards so a new credential shows up here. */
  refreshToken: number;
}) {
  const api = useCertForge();
  const [filters, setFilters] = useState<Filters>({
    q: "",
    status: "all",
    templateId: "",
    hideTest: false,
  });
  // The search box updates `search` on every keystroke; `filters.q` follows
  // it after a pause, so typing a name is one request rather than eight.
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<CredentialSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [templates, setTemplates] = useState<{ id: string; name: string }[]>([]);
  const [revoking, setRevoking] = useState<CredentialSummary | null>(null);
  // Bumped after a bulk resend so the list re-reads: queued rows leave the
  // "Email failed" filter and show as scheduled.
  const [reloadKey, setReloadKey] = useState(0);
  // The ceiling resend stops at, from the API, so "1 of 3 attempts left" is
  // never a number this file made up.
  const [attemptsMax, setAttemptsMax] = useState<number | null>(null);
  // Org-wide counts of emails needing attention, independent of the filter
  // in use: 43 failed rows scattered through 89 were only findable by
  // switching to "Email failed", which you had to already know to do.
  const [attention, setAttention] = useState<{ failed: number; deferred: number } | null>(null);
  // Rows with a resend in flight. A second click on the same row used to
  // send a second email and spend a second attempt.
  const [sending, setSending] = useState<ReadonlySet<string>>(new Set());

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => (current.q === search ? current : { ...current, q: search }));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Org templates and the global ones: a credential issued before the org
  // had its own design names a global template.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.listOrgTemplates(slug, controller.signal),
      api.listGlobalTemplates(controller.signal),
    ])
      .then(([own, global]) => {
        const seen = new Set<string>();
        setTemplates(
          [...own, ...global]
            .filter((tpl) => (seen.has(tpl.id) ? false : (seen.add(tpl.id), true)))
            .map((tpl) => ({ id: tpl.id, name: tpl.name })),
        );
      })
      // The template filter is a convenience; without the list it is hidden.
      .catch(() => {
        if (!controller.signal.aborted) setTemplates([]);
      });
    return () => controller.abort();
  }, [api, slug]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .listOrgCredentials(slug, { limit: PAGE_SIZE, ...toQuery(filters) }, controller.signal)
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
        setCursor(page.next_cursor);
        setAttemptsMax(page.delivery_attempts_max ?? null);
        setError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setItems(null);
        setError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, slug, filters, refreshToken, reloadKey]);

  useEffect(() => {
    const controller = new AbortController();
    const test = filters.hideTest ? ("exclude" as const) : undefined;
    Promise.all([
      api.listOrgCredentials(slug, { limit: 1, deliveryStatus: "failed", test }, controller.signal),
      api.listOrgCredentials(slug, { limit: 1, deliveryStatus: "deferred", test }, controller.signal),
    ])
      .then(([failed, deferred]) => setAttention({ failed: failed.total, deferred: deferred.total }))
      // A summary, not the list: without it the banner is simply absent.
      .catch(() => {
        if (!controller.signal.aborted) setAttention(null);
      });
    return () => controller.abort();
  }, [api, slug, refreshToken, reloadKey, filters.hideTest]);

  // Confirmations clear themselves; errors stay until dismissed or replaced.
  useEffect(() => {
    if (notice?.tone !== "ok") return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await api.listOrgCredentials(slug, {
        limit: PAGE_SIZE,
        cursor,
        ...toQuery(filters),
      });
      setItems((current) => [...(current ?? []), ...page.items]);
      setTotal(page.total);
      setCursor(page.next_cursor);
    } catch (err) {
      setNotice({ tone: "bad", text: toApiError(err).message });
    } finally {
      setLoadingMore(false);
    }
  }

  function patchRow(id: string, patch: Partial<CredentialSummary>) {
    setItems((current) =>
      current ? current.map((row) => (row.id === id ? { ...row, ...patch } : row)) : current,
    );
  }

  async function resend(row: CredentialSummary) {
    if (sending.has(row.id)) return;
    setNotice(null);
    setSending((current) => new Set(current).add(row.id));
    try {
      const result = await api.resendCredential(slug, row.id);
      patchRow(row.id, {
        delivery_status: result.delivery.status,
        delivery_next_attempt_at: result.delivery.next_attempt_at,
        delivery_error: result.delivery.error,
        delivery_attempts: result.delivery.attempts,
      });
      setAttention((current) =>
        current && row.delivery_status === "failed" && result.delivery.status !== "failed"
          ? {
              failed: Math.max(0, current.failed - 1),
              deferred: current.deferred + (result.delivery.status === "deferred" ? 1 : 0),
            }
          : current,
      );
      setNotice(
        result.sent
          ? { tone: "ok", text: `Email sent to ${row.recipient_email}.` }
          : result.delivery.status === "deferred"
            ? {
                tone: "ok",
                text: `The email provider's daily limit is reached. The email to ${row.recipient_email} will send automatically once it resets.`,
              }
            : {
              tone: "bad",
              text: `The email to ${row.recipient_email} did not send: ${result.delivery.error ?? "no reason given"}.`,
            },
      );
    } catch (err) {
      setNotice({ tone: "bad", text: toApiError(err).message });
    } finally {
      setSending((current) => {
        const next = new Set(current);
        next.delete(row.id);
        return next;
      });
    }
  }

  async function confirmRevoke(row: CredentialSummary) {
    try {
      await api.revokeCredential(slug, row.id);
      patchRow(row.id, { status: "revoked" });
      setNotice({ tone: "ok", text: `Revoked ${row.id}. Its verify page now says so.` });
    } catch (err) {
      const error = toApiError(err);
      setNotice({
        tone: "bad",
        text:
          error.status === 403
            ? "Only an owner or admin can revoke a credential."
            : error.message,
      });
    } finally {
      setRevoking(null);
    }
  }

  const filtered =
    filters.q.trim() !== "" || filters.status !== "all" || filters.templateId !== "" || filters.hideTest;

  return (
    <section className="rounded-2xl border border-hair bg-surface p-6">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium uppercase tracking-wider text-muted">Credentials</h3>
          <p className="mt-1 text-xs text-faint">
            Every certificate you have issued, one per person. Each has a PDF, a verify link
            anyone can check, and a digital badge.
          </p>
        </div>
        {items ? (
          <span className="text-sm text-faint">
            {total} {filtered ? "matching" : "total"}
          </span>
        ) : null}
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
        <label className="block">
          <span className="sr-only">Search credentials</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name, email or title"
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="sr-only">Filter by status</span>
          <select
            value={filters.status}
            onChange={(event) =>
              setFilters({ ...filters, status: event.target.value as StatusFilter })
            }
            className={inputClass}
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {templates.length > 0 ? (
          <label className="block">
            <span className="sr-only">Filter by template</span>
            <select
              value={filters.templateId}
              onChange={(event) => setFilters({ ...filters, templateId: event.target.value })}
              className={inputClass}
            >
              <option value="">All templates</option>
              {templates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-3 sm:col-span-3">
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={filters.hideTest}
              onChange={(event) => setFilters({ ...filters, hideTest: event.target.checked })}
              className="h-4 w-4 accent-[var(--cf-accent)]"
            />
            Hide test credentials
          </label>
          {/* Offered only on the "Email failed" view, so what it acts on is
              exactly the list on screen: the same search, template and test
              filters go to the server, which counts before anyone confirms. */}
          {filters.status === "email_failed" && items && total > 0 ? (
            <ResendFailedButton
              slug={slug}
              scope={{
                q: filters.q.trim() || undefined,
                templateId: filters.templateId || undefined,
                test: filters.hideTest ? "exclude" : undefined,
              }}
              onQueued={(result) => {
                setNotice({ tone: "ok", text: describeQueued(result) });
                setReloadKey((n) => n + 1);
              }}
            />
          ) : null}
        </div>
      </div>

      <div aria-live="polite">
        {notice ? (
          <div
            className={`mb-4 flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${
              notice.tone === "ok"
                ? "border-accent-line bg-accent-wash text-accent"
                : "border-danger-line bg-danger-wash text-danger"
            }`}
          >
            <p>{notice.text}</p>
            <button
              type="button"
              onClick={() => setNotice(null)}
              aria-label="Dismiss"
              className="-my-1 -mr-2 shrink-0 rounded px-2 py-1 leading-none opacity-70 transition-opacity hover:opacity-100"
            >
              ×
            </button>
          </div>
        ) : null}
      </div>

      {attention && filters.status !== "email_failed" && filters.status !== "email_scheduled" ? (
        <AttentionBanner
          slug={slug}
          failed={attention.failed}
          deferred={attention.deferred}
          hideTest={filters.hideTest}
          onShow={(status) => setFilters({ ...filters, status })}
          onQueued={(result) => {
            setNotice({ tone: "ok", text: describeQueued(result) });
            setReloadKey((n) => n + 1);
          }}
        />
      ) : null}

      {error ? (
        <ErrorNote>{error}</ErrorNote>
      ) : items === null ? (
        <Skeleton rows={4} />
      ) : items.length === 0 ? (
        <EmptyNote>{filtered ? "No credentials match these filters." : "Nothing issued yet."}</EmptyNote>
      ) : (
        <>
          <ul className="divide-y divide-hair">
            {items.map((credential) => (
              <li key={credential.id} className="flex items-start gap-3 py-3.5">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
                    <span className="truncate">{credential.recipient_name}</span>
                    {credential.is_test ? <StatusTag tone="neutral">Test</StatusTag> : null}
                    {credential.status === "revoked" ? <StatusTag tone="bad">Revoked</StatusTag> : null}
                    {credential.status === "pending" ? <StatusTag tone="neutral">Issuing</StatusTag> : null}
                    {credential.delivery_status === "failed" ? (
                      <StatusTag tone="bad">Email failed</StatusTag>
                    ) : credential.delivery_status === "deferred" ? (
                      <StatusTag tone="warn">Email scheduled</StatusTag>
                    ) : null}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {credential.recipient_email || "No email address"}
                    <span className="text-faint"> · {credential.title}</span>
                  </p>
                  <DeliveryDetail credential={credential} attemptsMax={attemptsMax} />
                  <p className="mt-1 text-xs text-faint">Issued {formatDate(credential.issued_at)}</p>
                </div>
                {credential.delivery_status === "failed" && canResend(credential, attemptsMax) ? (
                  <button
                    type="button"
                    onClick={() => resend(credential)}
                    disabled={sending.has(credential.id)}
                    aria-label={`Resend email to ${credential.recipient_name}`}
                    className={`${buttonClass("secondary", "sm")} shrink-0`}
                  >
                    {sending.has(credential.id) ? "Sending…" : "Resend"}
                  </button>
                ) : null}
                <RowActions
                  credential={credential}
                  canResend={canResend(credential, attemptsMax) && !sending.has(credential.id)}
                  onResend={() => resend(credential)}
                  onRevoke={() => setRevoking(credential)}
                  onCopied={() => setNotice({ tone: "ok", text: "Verify link copied." })}
                  onCopyFailed={() =>
                    setNotice({ tone: "bad", text: "Could not copy — the browser blocked the clipboard." })
                  }
                />
              </li>
            ))}
          </ul>
          {cursor ? (
            <div className="mt-4 flex justify-center">
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className={buttonClass("secondary", "sm")}
              >
                {loadingMore ? "Loading…" : `Show more (${items.length} of ${total})`}
              </button>
            </div>
          ) : null}
        </>
      )}

      <RevokeDialog
        credential={revoking}
        onCancel={() => setRevoking(null)}
        onConfirm={confirmRevoke}
      />
    </section>
  );
}

/** Whether a resend is possible at all: a live, non-test credential with an
 *  address and attempts left. The API enforces each of these; checking them
 *  here only spares a person a button that would be refused. */
function canResend(credential: CredentialSummary, attemptsMax: number | null): boolean {
  const live = credential.status === "issued" || credential.status === "claimed";
  const hasAttempts =
    attemptsMax === null || (credential.delivery_attempts ?? 0) < attemptsMax;
  return (
    live &&
    !credential.is_test &&
    credential.recipient_email.trim() !== "" &&
    credential.delivery_status !== "deferred" &&
    hasAttempts
  );
}

/** The why under a row that needs attention, and only those. Silent for
 *  `sent` and `not_requested`: a list that annotates every row annotates
 *  nothing. `unknown` is silent too — those rows predate delivery tracking,
 *  and labelling them would assert something we do not know. */
function DeliveryDetail({
  credential,
  attemptsMax,
}: {
  credential: CredentialSummary;
  attemptsMax: number | null;
}) {
  if (credential.delivery_status === "deferred") {
    const when = credential.delivery_next_attempt_at
      ? formatSendTime(credential.delivery_next_attempt_at)
      : null;
    return (
      <p className="mt-1 text-xs text-warn-ink">
        {when ? `Sends automatically after ${when}` : "Sends automatically"} — the email
        provider’s daily limit was reached.
      </p>
    );
  }
  if (credential.delivery_status !== "failed") return null;

  const used = credential.delivery_attempts ?? 0;
  const left = attemptsMax === null ? null : Math.max(0, attemptsMax - used);
  return (
    <p className="mt-1 truncate text-xs text-danger" title={credential.delivery_error ?? undefined}>
      {credential.delivery_error || "The email did not send."}
      {left !== null ? (
        <span className="text-muted">
          {" · "}
          {left === 0
            ? "no resends left"
            : `${left} of ${attemptsMax} ${left === 1 ? "attempt" : "attempts"} left`}
        </span>
      ) : null}
    </p>
  );
}

/** Above the list, whatever filter is on: how many emails need someone, with
 *  the two things a person does about it. Counts are the API's totals for
 *  `delivery_status`, never a count of the rows loaded on this page. */
function AttentionBanner({
  slug,
  failed,
  deferred,
  hideTest,
  onShow,
  onQueued,
}: {
  slug: string;
  failed: number;
  deferred: number;
  hideTest: boolean;
  onShow: (status: "email_failed" | "email_scheduled") => void;
  onQueued: Parameters<typeof ResendFailedButton>[0]["onQueued"];
}) {
  if (failed === 0 && deferred === 0) return null;
  return (
    <div className="mb-4 space-y-2">
      {failed > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-danger-line bg-danger-wash px-4 py-3">
          <p className="text-sm text-danger">
            <span className="font-medium">
              {failed} {failed === 1 ? "email" : "emails"} didn’t send.
            </span>{" "}
            The credentials are issued and verifiable; the recipients were not told.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onShow("email_failed")}
              className={buttonClass("quiet", "sm")}
            >
              Show them
            </button>
            <ResendFailedButton
              slug={slug}
              scope={{ test: hideTest ? "exclude" : undefined }}
              onQueued={onQueued}
            />
          </div>
        </div>
      ) : null}
      {deferred > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warn-line bg-warn-wash px-4 py-3">
          <p className="text-sm text-warn-ink">
            <span className="font-medium">
              {deferred} {deferred === 1 ? "email is" : "emails are"} scheduled.
            </span>{" "}
            The email provider’s daily limit was reached; they send automatically once it resets.
          </p>
          <button
            type="button"
            onClick={() => onShow("email_scheduled")}
            className={buttonClass("quiet", "sm")}
          >
            Show them
          </button>
        </div>
      ) : null}
    </div>
  );
}

function formatSendTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function RowActions({
  credential,
  canResend,
  onResend,
  onRevoke,
  onCopied,
  onCopyFailed,
}: {
  credential: CredentialSummary;
  /** Decided by the card: it also knows the attempt ceiling and which rows
   *  have a send in flight. */
  canResend: boolean;
  onResend: () => void;
  onRevoke: () => void;
  onCopied: () => void;
  onCopyFailed: () => void;
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  const live = credential.status === "issued" || credential.status === "claimed";
  const canRevoke = credential.status !== "revoked";

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    wrapper.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function run(action: () => void) {
    setOpen(false);
    action();
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(publicApi.verificationPageUrl(credential.id));
      onCopied();
    } catch {
      onCopyFailed();
    }
  }

  const item =
    "block w-full px-3 py-2 text-left text-sm text-ink no-underline transition-colors hover:bg-well focus-visible:bg-well focus-visible:outline-none";

  return (
    <div ref={wrapper} className="relative shrink-0">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Actions for ${credential.recipient_name}`}
        onClick={() => setOpen((current) => !current)}
        className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-well hover:text-ink"
      >
        <span aria-hidden className="text-lg leading-none">⋯</span>
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 z-20 mt-1 w-48 overflow-hidden rounded-lg border border-hair bg-surface py-1 shadow-[var(--cf-shadow-card)]"
        >
          {live ? (
            <button type="button" role="menuitem" className={item} onClick={() => run(copy)}>
              Copy verify link
            </button>
          ) : null}
          {live ? (
            <a
              role="menuitem"
              href={publicApi.certificatePdfUrl(credential.id)}
              target="_blank"
              rel="noreferrer"
              className={item}
              onClick={() => setOpen(false)}
            >
              Download PDF
            </a>
          ) : null}
          {canResend ? (
            <button type="button" role="menuitem" className={item} onClick={() => run(onResend)}>
              Resend email
            </button>
          ) : null}
          {canRevoke ? (
            <button
              type="button"
              role="menuitem"
              className={`${item} text-danger`}
              onClick={() => run(onRevoke)}
            >
              Revoke…
            </button>
          ) : null}
          {!live && !canRevoke ? (
            <p className="px-3 py-2 text-sm text-faint">No actions for a revoked credential.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** A native modal: focus trapping, Escape and the backdrop come with it. */
function RevokeDialog({
  credential,
  onCancel,
  onConfirm,
}: {
  credential: CredentialSummary | null;
  onCancel: () => void;
  onConfirm: (credential: CredentialSummary) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (credential && !node.open) node.showModal();
    if (!credential && node.open) node.close();
  }, [credential]);

  return (
    <dialog
      ref={dialog}
      onClose={onCancel}
      aria-labelledby="revoke-title"
      className="m-auto max-w-md rounded-xl border border-hair bg-surface p-6 text-ink shadow-[var(--cf-shadow-card)] backdrop:bg-ink/40"
    >
      {credential ? (
        <>
          <h2 id="revoke-title" className="font-display text-lg font-semibold">
            Revoke this credential?
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {credential.recipient_name}’s “{credential.title}” ({credential.id}) will show as
            revoked to anyone who verifies it, including from a printed QR code. This cannot be
            undone, and it does not return the credential to your monthly quota.
          </p>
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onCancel} className={buttonClass("secondary", "sm")}>
              Cancel
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                await onConfirm(credential);
                setBusy(false);
              }}
              className="inline-flex items-center justify-center rounded-lg bg-danger px-3 py-1.5 text-sm font-medium text-ground transition-colors disabled:cursor-not-allowed disabled:bg-well disabled:text-muted"
            >
              {busy ? "Revoking…" : "Revoke"}
            </button>
          </div>
        </>
      ) : null}
    </dialog>
  );
}
