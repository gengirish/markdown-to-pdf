"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  publicApi,
  toApiError,
  type CredentialListQuery,
  type CredentialSummary,
  type DeliveryStatus,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
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

type StatusFilter = "all" | "issued" | "revoked" | "email_failed";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "issued", label: "Issued" },
  { value: "revoked", label: "Revoked" },
  { value: "email_failed", label: "Email failed" },
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
    deliveryStatus: filters.status === "email_failed" ? "failed" : undefined,
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
        setError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setItems(null);
        setError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, slug, filters, refreshToken]);

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
    setNotice(null);
    try {
      const result = await api.resendCredential(slug, row.id);
      patchRow(row.id, { delivery_status: result.delivery.status });
      setNotice(
        result.sent
          ? { tone: "ok", text: `Email sent to ${row.recipient_email}.` }
          : {
              tone: "bad",
              text: `The email to ${row.recipient_email} did not send: ${result.delivery.error ?? "no reason given"}.`,
            },
      );
    } catch (err) {
      setNotice({ tone: "bad", text: toApiError(err).message });
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
        <label className="flex items-center gap-2 text-sm text-muted sm:col-span-3">
          <input
            type="checkbox"
            checked={filters.hideTest}
            onChange={(event) => setFilters({ ...filters, hideTest: event.target.checked })}
            className="h-4 w-4 accent-[var(--cf-accent)]"
          />
          Hide test credentials
        </label>
      </div>

      <div aria-live="polite">
        {notice ? (
          <p
            className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
              notice.tone === "ok"
                ? "border-accent-line bg-accent-wash text-accent"
                : "border-danger-line bg-danger-wash text-danger"
            }`}
          >
            {notice.text}
          </p>
        ) : null}
      </div>

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
              <li key={credential.id} className="flex items-start gap-3 py-3">
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    credential.status === "issued" || credential.status === "claimed"
                      ? "bg-accent"
                      : credential.status === "failed"
                        ? "bg-danger"
                        : "bg-well"
                  }`}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
                    <span className="truncate">{credential.recipient_name}</span>
                    {credential.is_test ? <StatusTag tone="neutral">Test</StatusTag> : null}
                    {credential.status === "revoked" ? <StatusTag tone="bad">Revoked</StatusTag> : null}
                  </p>
                  <p className="truncate text-xs text-muted">
                    {credential.recipient_email || "No email address"}
                  </p>
                  <p className="truncate text-xs text-faint">{credential.title}</p>
                  <p className="mt-1 text-xs text-faint">
                    {formatDate(credential.issued_at)} · {credential.status}
                    <DeliveryTag status={credential.delivery_status} />
                  </p>
                </div>
                <RowActions
                  credential={credential}
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

/** Flags the rows worth looking at. Deliberately silent for `sent` and
 *  `not_requested`: a list that tags every row tags nothing, and only a failure
 *  needs someone to act. `unknown` is silent too — those rows predate delivery
 *  tracking, and labelling them would assert something we do not know. */
function DeliveryTag({ status }: { status: DeliveryStatus | undefined }) {
  if (status !== "failed") return null;
  return (
    <>
      {" · "}
      <span className="text-warn-ink" title="The credential issued, but its email did not send">
        email failed
      </span>
    </>
  );
}

function RowActions({
  credential,
  onResend,
  onRevoke,
  onCopied,
  onCopyFailed,
}: {
  credential: CredentialSummary;
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
  const canResend = live && !credential.is_test && credential.recipient_email.trim() !== "";
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
