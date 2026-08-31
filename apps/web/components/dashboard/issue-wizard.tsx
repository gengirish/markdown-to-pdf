"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { buildCsv, LOOSE_EMAIL, parseCsv, type ParsedCsv } from "@/lib/csv";
import {
  toApiError,
  type BatchDelivery,
  type BatchStatus,
  type TemplateSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import {
  Card,
  EmptyNote,
  ErrorNote,
  Eyebrow,
  Mono,
  Skeleton,
  StatusTag,
  buttonClass,
  inputClass,
} from "./ui";

/**
 * Bulk issuance as a four-step wizard: upload, review, sign, report.
 *
 * `POST /orgs/{slug}/credentials/bulk` is a single call — there is no
 * server-side dry run, no per-row skip, no duplicate-against-existing-org
 * check, and no signing-key selection (one HMAC secret per environment, not
 * chosen per issuance). Every "problem" this wizard finds in Step 1/2 is
 * therefore checked in the browser, against the file alone: a missing
 * required column, a malformed address, a duplicate email within the same
 * file. What the design behind this wizard called "domain has no MX record"
 * and "already issued" are not included — this repo cannot check either one
 * honestly without a capability that does not exist, and a fabricated
 * problem is worse than a missed one: it tells someone to fix something that
 * was never wrong.
 *
 * The four steps map onto three real states, not four:
 *   1 Upload  — nothing has left the browser
 *   2 Review  — nothing has left the browser
 *   3 Sign    — the CSV has been POSTed; polling `getBatch` until it settles
 *   4 Report  — the batch is terminal
 * Steps 1 and 2 are client-side, so "back" is free. Step 3 is not — once the
 * POST lands the batch exists and cannot be un-created, so the step
 * indicator only allows jumping to a step already reached.
 */

const TERMINAL_STATUSES = new Set(["completed", "completed_with_errors", "failed"]);
const POLL_INTERVAL_MS = 2000;

type Row = Record<string, string>;

type Problem =
  | { kind: "missing-name" }
  | { kind: "missing-title" }
  | { kind: "bad-email"; value: string }
  | { kind: "duplicate-email"; value: string; firstRow: number };

interface CheckedRow {
  /** 1-indexed position in the file, matching the row number the server's
   *  own validation error would name if this row were the one that failed. */
  n: number;
  row: Row;
  problems: Problem[];
}

interface ParseResult {
  parsed: ParsedCsv;
  checked: CheckedRow[];
  /** Columns the template needs (services/templates.py's custom_placeholders)
   *  that this file's header does not contain, exact case. A CSV column is a
   *  dict key server-side, keyed on the literal header text — `Cohort` and
   *  `cohort` are different columns to it even though they look the same. */
  missingColumns: string[];
  /** A required column is present, but under different case. Worth a
   *  specific note: this is the single most common reason a file "matches"
   *  by eye and is rejected anyway. */
  caseMismatches: { needed: string; found: string }[];
}

function describeProblem(problem: Problem): string {
  switch (problem.kind) {
    case "missing-name":
      return "Name column is empty";
    case "missing-title":
      return "Title column is empty";
    case "bad-email":
      return `“${problem.value}” doesn't look like an email address`;
    case "duplicate-email":
      return `Same email as row ${problem.firstRow}`;
  }
}

/** Every check the file gets before anything is uploaded. name/title mirror
 *  the exact rule `routes/studio.py` enforces server-side — a blank one fails
 *  the whole upload with a 400, not just that row, so catching it here is
 *  what makes "241 ready, 5 need a fix" possible instead of one all-or-nothing
 *  error naming a single row. Duplicate-email and malformed-email are not
 *  server rules; they are checked because the design this wizard is built
 *  from asked for them and both are honestly checkable from the file alone. */
function checkRows(parsed: ParsedCsv, template: TemplateSummary | undefined): ParseResult {
  const seenEmails = new Map<string, number>();
  const checked: CheckedRow[] = parsed.rows.map((row, index) => {
    const problems: Problem[] = [];
    const name = (row.name ?? "").trim();
    const title = (row.title ?? "").trim();
    const email = (row.email ?? "").trim();

    if (!name) problems.push({ kind: "missing-name" });
    if (!title) problems.push({ kind: "missing-title" });
    if (email && !LOOSE_EMAIL.test(email)) problems.push({ kind: "bad-email", value: email });
    if (email) {
      const key = email.toLowerCase();
      const first = seenEmails.get(key);
      if (first !== undefined) {
        problems.push({ kind: "duplicate-email", value: email, firstRow: first });
      } else {
        seenEmails.set(key, index + 1);
      }
    }

    return { n: index + 1, row, problems };
  });

  const missingColumns: string[] = [];
  const caseMismatches: { needed: string; found: string }[] = [];
  for (const needed of template?.variables ?? []) {
    if (parsed.header.includes(needed)) continue;
    const differentCase = parsed.header.find((h) => h.toLowerCase() === needed.toLowerCase());
    if (differentCase) caseMismatches.push({ needed, found: differentCase });
    else missingColumns.push(needed);
  }

  return { parsed, checked, missingColumns, caseMismatches };
}

function downloadFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const STEP_LABELS = ["Upload", "Review", "Sign", "Report"] as const;
type Step = 1 | 2 | 3 | 4;

export function IssueWizard({ slug, onIssued }: { slug: string; onIssued: () => void }) {
  const api = useCertForge();

  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState("");

  const [step, setStep] = useState<Step>(1);
  const [furthest, setFurthest] = useState<Step>(1);

  const [file, setFile] = useState<File | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [result, setResult] = useState<ParseResult | null>(null);

  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [edits, setEdits] = useState<Map<number, Row>>(new Map());

  const [issuing, setIssuing] = useState(false);
  const [issueError, setIssueError] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchStatus | null>(null);
  const [batchStartedAt, setBatchStartedAt] = useState<number | null>(null);

  const onIssuedRef = useRef(onIssued);
  useEffect(() => {
    onIssuedRef.current = onIssued;
  }, [onIssued]);

  const goTo = useCallback(
    (target: Step) => {
      if (target <= furthest) setStep(target);
    },
    [furthest],
  );

  const advance = useCallback((target: Step) => {
    setStep(target);
    setFurthest((current) => (target > current ? target : current));
  }, []);

  // Same template-loading shape as the single-issue card: org templates need
  // a role the viewer may not have, and that failure must not hide the global
  // list, which every member can always see.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    Promise.allSettled([
      api.listGlobalTemplates(controller.signal),
      api.listOrgTemplates(slug, controller.signal),
    ]).then((results) => {
      if (cancelled) return;
      const available = results.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
      if (results.every((r) => r.status === "rejected")) {
        const reason = results[0].status === "rejected" ? results[0].reason : null;
        setTemplatesError(toApiError(reason).message);
        setTemplates([]);
        return;
      }
      setTemplates(available);
      setTemplateId((current) => current || available[0]?.id || "");
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [api, slug]);

  const template = templates?.find((t) => t.id === templateId);

  // Re-parsed whenever the file or the chosen template changes — the template
  // decides which extra columns are required, so switching templates can turn
  // a clean file into one missing a column, or the reverse.
  useEffect(() => {
    if (!file) {
      setResult(null);
      return;
    }
    setParseError(null);
    file
      .text()
      .then((text) => {
        const parsed = parseCsv(text);
        if (parsed.rows.length === 0) {
          setParseError("That file has no data rows.");
          setResult(null);
          return;
        }
        setResult(checkRows(parsed, template));
        setExcluded(new Set());
        setEdits(new Map());
      })
      .catch(() => setParseError("Could not read that file as text."));
    // template is read at the moment of parsing, not tracked as a dependency
    // on its own object identity — it is refetched with a new reference every
    // poll of the template list, which would otherwise re-parse constantly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, templateId]);

  const flagged = useMemo(
    () => result?.checked.filter((r) => r.problems.length > 0) ?? [],
    [result],
  );
  const clean = (result?.checked.length ?? 0) - flagged.length;

  const effectiveRow = useCallback(
    (checked: CheckedRow): Row => edits.get(checked.n) ?? checked.row,
    [edits],
  );

  const includedCount = (result?.checked.length ?? 0) - excluded.size;

  // Batch processing is asynchronous server-side; poll until it settles
  // rather than claiming a result the worker has not produced.
  useEffect(() => {
    if (!batch || TERMINAL_STATUSES.has(batch.status)) return;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .getBatch(slug, batch.id, controller.signal)
        .then((next) => {
          setBatch(next);
          if (TERMINAL_STATUSES.has(next.status)) {
            onIssuedRef.current();
            advance(4);
          }
        })
        .catch(() => {
          // Leave the last known status on screen; the next render will retry.
        });
    }, POLL_INTERVAL_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, slug, batch, advance]);

  const startIssuance = useCallback(async () => {
    if (!result || !templateId) return;
    const rows = result.checked
      .filter((r) => !excluded.has(r.n))
      .map((r) => effectiveRow(r));
    if (rows.length === 0) return;

    const csv = buildCsv(result.parsed.header, rows);
    const csvFile = new File([csv], file?.name ?? "cohort.csv", { type: "text/csv" });

    advance(3);
    setIssuing(true);
    setIssueError(null);
    setBatchStartedAt(Date.now());
    try {
      const uploaded = await api.bulkIssueFromCsv(slug, { templateId, file: csvFile });
      setBatch({
        id: uploaded.batch_id,
        status: uploaded.status,
        total: uploaded.total,
        succeeded: 0,
        failed: 0,
        // Zeroes are honest here — the worker has not run yet.
        delivery: { delivered: 0, failed: 0, not_requested: 0 },
        error_report: null,
        created_at: new Date().toISOString(),
        completed_at: null,
      });
    } catch (err) {
      // Stays on Step 3 -- that is where the error branch lives. Advancing
      // back to Step 2 here would leave the failure screen unseen on the
      // first attempt, which is what an earlier version of this did.
      setIssueError(toApiError(err).message);
    } finally {
      setIssuing(false);
    }
  }, [api, slug, templateId, result, excluded, effectiveRow, file, advance]);

  const startOver = useCallback(() => {
    setFile(null);
    setResult(null);
    setExcluded(new Set());
    setEdits(new Map());
    setBatch(null);
    setIssueError(null);
    setStep(1);
    setFurthest(1);
  }, []);

  const noTemplates = templates !== null && templates.length === 0;
  const canProceedStep1 = Boolean(
    result && result.missingColumns.length === 0 && result.checked.length > 0,
  );

  return (
    <Card
      title="Issue a cohort"
      description="Upload once, review what needs a fix, then sign and issue the rest."
    >
      <StepBar step={step} furthest={furthest} onGo={goTo} />

      {step === 1 ? (
        <StepUpload
          templates={templates}
          templatesError={templatesError}
          noTemplates={noTemplates}
          template={template}
          templateId={templateId}
          onTemplateChange={setTemplateId}
          file={file}
          onFile={setFile}
          parseError={parseError}
          result={result}
          clean={clean}
          flaggedCount={flagged.length}
          onContinue={() => advance(2)}
          canContinue={canProceedStep1}
        />
      ) : null}

      {step === 2 && result ? (
        <StepReview
          flagged={flagged}
          excluded={excluded}
          effectiveRow={effectiveRow}
          onExclude={(n, value) =>
            setExcluded((current) => {
              const next = new Set(current);
              if (value) next.add(n);
              else next.delete(n);
              return next;
            })
          }
          onExcludeAll={() => setExcluded(new Set(flagged.map((r) => r.n)))}
          onEdit={(n, patch) =>
            setEdits((current) => {
              const next = new Map(current);
              const row = result.checked.find((r) => r.n === n);
              if (!row) return current;
              next.set(n, { ...effectiveRow(row), ...patch });
              return next;
            })
          }
          onDownloadFlagged={() => {
            const rows = flagged.map((r) => effectiveRow(r));
            downloadFile(
              "rows-needing-a-fix.csv",
              buildCsv(result.parsed.header, rows),
              "text/csv",
            );
          }}
          includedCount={includedCount}
          templateName={template?.name ?? ""}
          onBack={() => goTo(1)}
          onIssue={startIssuance}
          issuing={issuing}
        />
      ) : null}

      {step === 3 ? (
        <StepSign
          batch={batch}
          issueError={issueError}
          startedAt={batchStartedAt}
          hadAnyEmail={Boolean(
            result?.checked.some((r) => effectiveRow(r).email?.trim() && !excluded.has(r.n)),
          )}
          onSkipToReport={() => batch && TERMINAL_STATUSES.has(batch.status) && advance(4)}
          onBackToReview={() => goTo(2)}
        />
      ) : null}

      {step === 4 && batch ? (
        <StepReport
          batch={batch}
          excludedCount={excluded.size}
          flaggedTotal={flagged.length}
          onResolveFlagged={() => goTo(2)}
          onStartOver={startOver}
        />
      ) : null}
    </Card>
  );
}

function StepBar({
  step,
  furthest,
  onGo,
}: {
  step: Step;
  furthest: Step;
  onGo: (step: Step) => void;
}) {
  return (
    <div className="mb-7 grid grid-cols-4 gap-1 rounded-lg bg-well p-1">
      {STEP_LABELS.map((label, index) => {
        const n = (index + 1) as Step;
        const active = n === step;
        const reachable = n <= furthest;
        const done = n < step;
        return (
          <button
            key={label}
            type="button"
            disabled={!reachable}
            onClick={() => onGo(n)}
            className={`flex items-center justify-center gap-2 rounded-md px-2 py-2.5 text-xs font-medium transition-colors ${
              active
                ? "bg-surface text-ink shadow-[var(--cf-shadow-card)]"
                : reachable
                  ? "text-accent hover:bg-surface/60"
                  : "cursor-not-allowed text-faint"
            }`}
          >
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full font-mono text-[9px] ${
                active
                  ? "bg-ink text-ground"
                  : done
                    ? "bg-accent text-ground"
                    : "bg-hair-strong text-muted"
              }`}
            >
              {done ? "✓" : index + 1}
            </span>
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ── Step 1 — Upload ─────────────────────────────────────────────────────────

function StepUpload({
  templates,
  templatesError,
  noTemplates,
  template,
  templateId,
  onTemplateChange,
  file,
  onFile,
  parseError,
  result,
  clean,
  flaggedCount,
  onContinue,
  canContinue,
}: {
  templates: TemplateSummary[] | null;
  templatesError: string | null;
  noTemplates: boolean;
  template: TemplateSummary | undefined;
  templateId: string;
  onTemplateChange: (id: string) => void;
  file: File | null;
  onFile: (file: File | null) => void;
  parseError: string | null;
  result: ParseResult | null;
  clean: number;
  flaggedCount: number;
  onContinue: () => void;
  canContinue: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
      <div>
        {templates === null ? (
          <Skeleton rows={1} />
        ) : templatesError ? (
          <ErrorNote>Could not load templates: {templatesError}</ErrorNote>
        ) : noTemplates ? (
          <EmptyNote>
            No templates are available to this organization yet, so credentials cannot be issued.
          </EmptyNote>
        ) : (
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">Template</span>
            <select
              value={templateId}
              onChange={(event) => onTemplateChange(event.target.value)}
              className={inputClass}
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {t.is_default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="group relative mt-5 overflow-hidden rounded-xl border-2 border-dashed border-hair p-10 text-center transition-colors hover:border-accent">
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => onFile(event.target.files?.[0] ?? null)}
            className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
          />
          <p className="mb-1 text-sm font-medium text-ink">
            {file ? file.name : "Click or drop a CSV file here"}
          </p>
          <p className="text-xs text-faint">
            Nothing is uploaded here — this file is only read in your browser.
          </p>
        </div>

        {parseError ? (
          <div className="mt-4">
            <ErrorNote>{parseError}</ErrorNote>
          </div>
        ) : null}

        {result ? (
          <div className="mt-5 space-y-4">
            {result.missingColumns.length > 0 ? (
              <ErrorNote>
                This template needs{" "}
                {result.missingColumns.map((c) => (
                  <Mono key={c} className="text-danger">
                    {c}
                  </Mono>
                ))}{" "}
                — {result.missingColumns.length === 1 ? "a column this" : "columns this"} file
                doesn&apos;t have.
              </ErrorNote>
            ) : null}
            {result.caseMismatches.map(({ needed, found }) => (
              <ErrorNote key={needed}>
                This template needs a column named exactly <Mono>{needed}</Mono>, and the file has{" "}
                <Mono>{found}</Mono> instead — same word, different case, and the server matches
                exactly.
              </ErrorNote>
            ))}

            <div className="grid grid-cols-3 divide-x divide-hair-soft rounded-lg border border-hair-soft bg-sunken">
              <Stat value={String(clean)} label="ready to issue" tone="ok" />
              <Stat
                value={String(flaggedCount)}
                label="need a fix"
                tone={flaggedCount > 0 ? "warn" : "neutral"}
              />
              <Stat value={String(result.checked.length)} label="rows total" tone="neutral" />
            </div>
          </div>
        ) : null}

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onContinue}
            disabled={!canContinue}
            className={buttonClass("primary")}
          >
            {flaggedCount > 0
              ? `Review ${flaggedCount} flagged row${flaggedCount === 1 ? "" : "s"}`
              : "Continue to review"}
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-hair-soft bg-sunken p-5">
        <div className="mb-3">
          <Eyebrow>Template</Eyebrow>
        </div>
        {template ? (
          <div className="space-y-2.5 text-sm">
            <Row2 label="Name" value={template.name} />
            <Row2 label="Form" value={template.is_guided ? "Guided" : "Custom HTML"} />
            <Row2
              label="Extra columns"
              value={template.variables.length > 0 ? template.variables.join(", ") : "None"}
            />
          </div>
        ) : (
          <p className="text-sm text-faint">Choose a template to see what it requires.</p>
        )}
        <div className="mt-4 h-px bg-hair-soft" />
        <p className="mt-4 text-xs leading-relaxed text-faint">
          Every row needs <Mono>name</Mono> and <Mono>title</Mono> columns, exact lowercase.{" "}
          <Mono>email</Mono> is optional — a row with no address is issued without an attempt to
          send it anywhere.
        </p>
      </div>
    </div>
  );
}

function Stat({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone: "ok" | "warn" | "neutral";
}) {
  const color = tone === "ok" ? "text-accent" : tone === "warn" ? "text-warn-ink" : "text-ink";
  return (
    <div className="px-4 py-4 text-center">
      <div className={`font-display text-2xl font-semibold leading-none ${color}`}>{value}</div>
      <div className="mt-1.5 text-[11px] text-faint">{label}</div>
    </div>
  );
}

function Row2({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-faint">{label}</span>
      <span className="text-right text-ink">{value}</span>
    </div>
  );
}

// ── Step 2 — Review ──────────────────────────────────────────────────────────

function StepReview({
  flagged,
  excluded,
  effectiveRow,
  onExclude,
  onExcludeAll,
  onEdit,
  onDownloadFlagged,
  includedCount,
  templateName,
  onBack,
  onIssue,
  issuing,
}: {
  flagged: CheckedRow[];
  excluded: Set<number>;
  effectiveRow: (row: CheckedRow) => Row;
  onExclude: (n: number, value: boolean) => void;
  onExcludeAll: () => void;
  onEdit: (n: number, patch: Row) => void;
  onDownloadFlagged: () => void;
  includedCount: number;
  templateName: string;
  onBack: () => void;
  onIssue: () => void;
  issuing: boolean;
}) {
  if (flagged.length === 0) {
    return (
      <div>
        <EmptyNote>Every row looks ready — nothing here needs a fix.</EmptyNote>
        <div className="mt-6 flex justify-between">
          <button type="button" onClick={onBack} className={buttonClass("quiet")}>
            Back
          </button>
          <button
            type="button"
            onClick={onIssue}
            disabled={issuing}
            className={buttonClass("primary")}
          >
            {issuing ? "Starting…" : `Sign and issue ${includedCount}`}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-lg font-semibold text-ink">
            {flagged.length} row{flagged.length === 1 ? "" : "s"} need
            {flagged.length === 1 ? "s" : ""} a fix
          </h3>
          <p className="mt-1 text-sm text-muted">
            Fix a value inline, or exclude a row and issue the rest.
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onExcludeAll} className={buttonClass("secondary", "sm")}>
            Exclude all {flagged.length}
          </button>
          <button
            type="button"
            onClick={onDownloadFlagged}
            className={buttonClass("secondary", "sm")}
          >
            Download these rows
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-hair-soft">
        <table className="w-full min-w-[520px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-hair-soft bg-sunken text-left text-xs uppercase tracking-[0.06em] text-faint">
              <th className="w-12 px-3 py-2.5 font-medium">Row</th>
              <th className="px-3 py-2.5 font-medium">Name</th>
              <th className="px-3 py-2.5 font-medium">Email</th>
              <th className="px-3 py-2.5 font-medium">Problem</th>
              <th className="w-24 px-3 py-2.5 font-medium">Exclude</th>
            </tr>
          </thead>
          <tbody>
            {flagged.map((r) => {
              const row = effectiveRow(r);
              const isOut = excluded.has(r.n);
              return (
                <tr
                  key={r.n}
                  className={`border-b border-hair-soft last:border-0 ${isOut ? "opacity-40" : ""}`}
                >
                  <td className="px-3 py-2 font-mono text-xs text-faint">{r.n}</td>
                  <td className="px-3 py-2">
                    <input
                      value={row.name ?? ""}
                      disabled={isOut}
                      onChange={(e) => onEdit(r.n, { name: e.target.value })}
                      className="w-full rounded border border-hair bg-surface px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={row.email ?? ""}
                      disabled={isOut}
                      onChange={(e) => onEdit(r.n, { email: e.target.value })}
                      className="w-full rounded border border-hair bg-surface px-2 py-1 font-mono text-xs text-ink focus:border-accent focus:outline-none"
                    />
                  </td>
                  <td className="px-3 py-2 text-xs text-warn-ink">
                    {r.problems.map(describeProblem).join("; ")}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={isOut}
                      onChange={(e) => onExclude(r.n, e.target.checked)}
                      className="h-4 w-4 rounded border-hair-strong"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <div className="text-sm text-muted">
          <span className="font-medium text-ink">{includedCount}</span> row
          {includedCount === 1 ? "" : "s"} will be issued against{" "}
          <span className="font-medium text-ink">{templateName || "this template"}</span>.
        </div>
        <div className="flex gap-3">
          <button type="button" onClick={onBack} className={buttonClass("quiet")}>
            Back
          </button>
          <button
            type="button"
            onClick={onIssue}
            disabled={issuing || includedCount === 0}
            className={buttonClass("primary")}
          >
            {issuing ? "Starting…" : `Sign and issue ${includedCount}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Step 3 — Sign ────────────────────────────────────────────────────────────

function StepSign({
  batch,
  issueError,
  startedAt,
  hadAnyEmail,
  onSkipToReport,
  onBackToReview,
}: {
  batch: BatchStatus | null;
  issueError: string | null;
  startedAt: number | null;
  hadAnyEmail: boolean;
  onSkipToReport: () => void;
  /** Preserves the uploaded file and every edit -- goTo(2), not a reset.
   *  "Start a new batch" (a full reset) belongs on the Report step, once a
   *  batch exists to report on -- not on a Sign-step error, where the
   *  person's edits are the thing worth keeping. */
  onBackToReview: () => void;
}) {
  const settled = batch ? TERMINAL_STATUSES.has(batch.status) : false;

  // Date.now() cannot be read during render -- it is impure, and nothing here
  // would re-render on its own as time passes anyway. A one-second ticker
  // owns the clock instead, and stops once the batch settles rather than
  // ticking a finished screen forever. Declared before any early return: the
  // rules of hooks require the same hooks in the same order on every render,
  // and this component has two returns above the content that uses it.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (settled) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [settled]);

  if (issueError) {
    return (
      <div>
        <ErrorNote>{issueError}</ErrorNote>
        <div className="mt-6">
          <button type="button" onClick={onBackToReview} className={buttonClass("secondary")}>
            Back to review
          </button>
        </div>
      </div>
    );
  }

  if (!batch) {
    return <Skeleton rows={3} />;
  }

  const pct = batch.total > 0 ? Math.round((batch.succeeded / batch.total) * 100) : 0;
  const elapsedSec = startedAt ? Math.max(0, Math.round((now - startedAt) / 1000)) : 0;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold text-ink">
          {settled ? "Batch finished" : `Signing batch · ${pct}%`}
        </h3>
        <span className="font-mono text-xs text-faint">
          {batch.succeeded + batch.failed} / {batch.total} · {elapsedSec}s
        </span>
      </div>

      <div className="mb-6 h-2 overflow-hidden rounded-full bg-well">
        <div
          className="h-full bg-accent transition-[width] duration-500"
          style={{ width: `${settled ? 100 : pct}%` }}
        />
      </div>

      <ul className="mb-6 list-none space-y-2 p-0 text-sm text-muted">
        <ChecklistItem done>Template resolved</ChecklistItem>
        <ChecklistItem done={batch.succeeded > 0 || settled}>
          {batch.succeeded} of {batch.total} credential documents rendered
        </ChecklistItem>
        <ChecklistItem done={batch.succeeded > 0 || settled}>
          HMAC-SHA256 signatures written — {batch.succeeded} so far
        </ChecklistItem>
        <ChecklistItem done={settled}>
          {hadAnyEmail
            ? "Delivery attempted for every row with an address"
            : "No delivery attempted — no row in this batch has an address"}
        </ChecklistItem>
      </ul>

      <p className="mb-6 text-xs leading-relaxed text-faint">
        This keeps running even if you close this tab — the batch is processed on the server, not
        in your browser. Come back to Recent credentials to see the result if you leave now.
      </p>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onSkipToReport}
          disabled={!settled}
          className={buttonClass("primary")}
        >
          {settled ? "See the report" : "Waiting on the worker…"}
        </button>
      </div>
    </div>
  );
}

function ChecklistItem({ done, children }: { done: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2.5">
      <span
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] ${
          done ? "bg-accent text-ground" : "bg-well text-faint"
        }`}
      >
        {done ? "✓" : "·"}
      </span>
      <span className={done ? "text-ink" : ""}>{children}</span>
    </li>
  );
}

// ── Step 4 — Report ──────────────────────────────────────────────────────────

function StepReport({
  batch,
  excludedCount,
  flaggedTotal,
  onResolveFlagged,
  onStartOver,
}: {
  batch: BatchStatus;
  excludedCount: number;
  flaggedTotal: number;
  onResolveFlagged: () => void;
  onStartOver: () => void;
}) {
  const failed = batch.status === "failed";
  const durationSec =
    batch.completed_at && batch.created_at
      ? Math.max(
          0,
          Math.round(
            (new Date(batch.completed_at).getTime() - new Date(batch.created_at).getTime()) /
              1000,
          ),
        )
      : null;

  const errorEntries =
    batch.error_report && typeof batch.error_report === "object"
      ? Object.entries(batch.error_report as Record<string, string>)
      : [];

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <span
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border text-lg ${
              failed
                ? "border-danger-line bg-danger-wash text-danger"
                : "border-accent-line bg-accent-wash text-accent"
            }`}
          >
            {failed ? "!" : "✓"}
          </span>
          <div>
            <h3 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
              {batch.succeeded} credential{batch.succeeded === 1 ? "" : "s"} issued
            </h3>
            <p className="mt-1 text-sm text-muted">
              Batch <Mono>{batch.id}</Mono>
              {durationSec !== null ? ` · ${durationSec}s` : ""}
            </p>
          </div>
        </div>
        <StatusTag tone={failed ? "bad" : batch.failed > 0 ? "warn" : "ok"}>
          {batch.status.replace(/_/g, " ")}
        </StatusTag>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-hair-soft bg-sunken p-5">
          <div className="mb-2">
            <Eyebrow>Rendering</Eyebrow>
          </div>
          <p className="text-sm text-ink">
            {batch.succeeded} of {batch.total} rendered and signed.
            {batch.failed > 0 ? ` ${batch.failed} failed — see below.` : ""}
          </p>
        </div>
        <div className="rounded-lg border border-hair-soft bg-sunken p-5">
          <div className="mb-2">
            <Eyebrow>Delivery</Eyebrow>
          </div>
          <DeliveryLine delivery={batch.delivery} />
        </div>
      </div>

      {excludedCount > 0 ? (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-warn-line bg-warn-wash px-5 py-4">
          <p className="text-sm text-warn-ink">
            {excludedCount} of {flaggedTotal} flagged row{flaggedTotal === 1 ? "" : "s"} were held
            back and not issued.
          </p>
          <button
            type="button"
            onClick={onResolveFlagged}
            className="text-xs text-warn-ink underline"
          >
            Review them
          </button>
        </div>
      ) : null}

      {errorEntries.length > 0 ? (
        <div className="mt-4">
          <div className="mb-2">
            <Eyebrow tone="muted">{errorEntries.length} rendering failures</Eyebrow>
          </div>
          <div className="max-h-48 overflow-y-auto rounded-lg border border-hair-soft">
            {errorEntries.map(([id, message]) => (
              <div
                key={id}
                className="flex items-start gap-3 border-b border-hair-soft px-4 py-2.5 text-xs last:border-0"
              >
                <Mono className="shrink-0 text-faint">{id}</Mono>
                <span className="text-danger">{message}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-7 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => {
            const lines = [
              `Batch,${batch.id}`,
              `Status,${batch.status}`,
              `Total,${batch.total}`,
              `Succeeded,${batch.succeeded}`,
              `Failed,${batch.failed}`,
              `Delivered,${batch.delivery?.delivered ?? ""}`,
              `Delivery failed,${batch.delivery?.failed ?? ""}`,
              `Not requested,${batch.delivery?.not_requested ?? ""}`,
              "",
              "credential_id,error",
              ...errorEntries.map(([id, msg]) => `${id},"${msg.replace(/"/g, '""')}"`),
            ];
            downloadFile(`batch-${batch.id}-report.csv`, lines.join("\r\n"), "text/csv");
          }}
          className={buttonClass("secondary")}
        >
          Download batch report
        </button>
        <a href="#recent-credentials" className={`${buttonClass("secondary")} no-underline`}>
          See it in Recent credentials
        </a>
        <button type="button" onClick={onStartOver} className={buttonClass("quiet")}>
          Start a new batch
        </button>
      </div>
    </div>
  );
}

/** Issued and delivered are different numbers. Saying "30 issued" while 30
 *  emails failed is how a batch that reached nobody read as a clean success. */
function DeliveryLine({ delivery }: { delivery: BatchDelivery | undefined }) {
  if (!delivery) return <p className="text-sm text-faint">No delivery information.</p>;

  const { delivered, failed, not_requested: notRequested } = delivery;

  if (failed === 0 && delivered === 0 && notRequested > 0) {
    return (
      <p className="text-sm text-ink">
        No emails sent — {notRequested === 1 ? "the row had" : "the rows had"} no address, or
        delivery was not requested.
      </p>
    );
  }

  const parts = [`${delivered} delivered`];
  if (failed > 0) parts.push(`${failed} failed`);
  if (notRequested > 0) parts.push(`${notRequested} not sent`);

  return (
    <p className={`text-sm ${failed > 0 ? "font-medium text-warn-ink" : "text-ink"}`}>
      {parts.join(", ")}.{failed > 0 ? " Failed sends are retried automatically." : ""}
    </p>
  );
}
