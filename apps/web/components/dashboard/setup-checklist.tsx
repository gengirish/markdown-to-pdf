"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { type OrgProfile } from "@/lib/api";
import {
  buildSteps,
  checklistMode,
  nextStep,
  orderSteps,
  progressSegments,
  stepsLeftLabel,
  type Counts,
  type Step,
  type StepTab,
} from "@/lib/setup-steps";
import { useCertForge } from "@/lib/use-api";
import { buttonClass, Eyebrow } from "./ui";

/** The three things a new organization does before CertForge is theirs.
 *
 *  Every tick is read off real state — the org profile, the org's own
 *  templates, and its credential count — never a flag set when someone clicked
 *  a button. A checklist that says "done" because a form was opened is the
 *  fabricated-data failure this app has shipped before.
 *
 *  Nothing is locked. Issuance falls back to the global default template, so
 *  an org can issue on step one; the other two make the result look like it
 *  came from them. Gating the valuable step behind the cosmetic ones would put
 *  the least important work in front of the only moment that matters.
 *
 *  It sits above every tab, so it shrinks once it has done its job: the full
 *  card only until the first credential is out, then a one-line banner (see
 *  `checklistMode`), then nothing once every step is done.
 */

export function SetupChecklist({
  slug,
  org,
  refreshKey,
  onSelectTab,
}: {
  slug: string;
  org: OrgProfile | null;
  /** Changes whenever something on the dashboard might have moved a step:
   *  a credential issued, or a tab left after editing templates. */
  refreshKey: string;
  onSelectTab: (tab: StepTab) => void;
}) {
  const api = useCertForge();
  const [counts, setCounts] = useState<Counts | null>(null);
  const [failed, setFailed] = useState(false);
  // Storage through useSyncExternalStore, never a lazy initializer: the
  // server has no storage, and a first render that differs between the two
  // passes is a hydration mismatch (see apps/web/CLAUDE.md, "Theme"). The
  // server snapshot is null — "not read yet" — and React swaps in the real
  // value before the first paint, so a dismissed checklist never flashes its
  // placeholder. Nothing else writes the key, so there is nothing to subscribe
  // to; a dismissal in this tab goes through `dismissed`.
  const stored = useSyncExternalStore(
    noSubscription,
    () => readHidden(slug),
    () => null,
  );
  const [dismissed, setDismissed] = useState(false);
  const hidden = dismissed || stored;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.listOrgTemplates(slug, controller.signal),
      api.listOrgCredentials(slug, { limit: 1 }, controller.signal),
    ])
      .then(([templates, credentials]) => {
        setCounts({ templates: templates.length, credentials: credentials.total });
        setFailed(false);
      })
      // Guidance, not data: a failed load hides the checklist rather than
      // guessing at progress. The cards below report their own errors.
      .catch(() => {
        if (controller.signal.aborted) return;
        setCounts(null);
        setFailed(true);
      });
    return () => controller.abort();
  }, [api, slug, refreshKey]);

  // Every step done retires the checklist for this org in this browser, the
  // same way dismissing it does — deleting a template later should not bring
  // a setup card back to an org that finished setting up.
  const complete =
    org !== null && counts !== null && checklistMode(buildSteps(org, counts)) === "complete";
  useEffect(() => {
    if (complete) writeHidden(slug);
  }, [complete, slug]);

  if (hidden !== false || failed) return null;
  // Hold the banner's height while progress loads, so the tab below does not
  // jump when it arrives. The banner is the likelier outcome for anyone
  // coming back; a brand-new org, which gets the full card, grows from here.
  if (!org || !counts) {
    return <div aria-hidden className="mb-8 h-12 animate-pulse rounded-xl bg-well" />;
  }

  return (
    <SetupChecklistView
      org={org}
      counts={counts}
      onSelectTab={onSelectTab}
      onHide={() => {
        writeHidden(slug);
        setDismissed(true);
      }}
    />
  );
}

/** The checklist itself, with no fetching — everything it shows is a function
 *  of its props. */
export function SetupChecklistView({
  org,
  counts,
  onSelectTab,
  onHide,
}: {
  org: OrgProfile;
  counts: Counts;
  onSelectTab: (tab: StepTab) => void;
  onHide: () => void;
}) {
  const steps = orderSteps(buildSteps(org, counts));
  const mode = checklistMode(steps);
  if (mode === "complete") return null;
  if (mode === "banner") {
    return <SetupBanner steps={steps} onSelectTab={onSelectTab} onHide={onHide} />;
  }
  const doneCount = steps.filter((step) => step.done).length;

  const nextId = nextStep(steps)?.id;
  const returning = doneCount > 0;

  return (
    <section
      aria-labelledby="setup-checklist-title"
      className="mb-8 rounded-xl border border-hair bg-surface p-6 shadow-[var(--cf-shadow-card)] sm:p-7"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Eyebrow tone="accent">{returning ? "Pick up where you left off" : "Getting started"}</Eyebrow>
          <h2
            id="setup-checklist-title"
            className="mt-3 font-display text-xl font-semibold tracking-[-0.02em] text-ink"
          >
            {returning ? `${doneCount} of ${steps.length} steps done.` : "Make CertForge yours."}
          </h2>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
            {summary(steps, org.name)}
          </p>
        </div>
        <button
          type="button"
          onClick={onHide}
          className={buttonClass("quiet", "sm")}
        >
          Hide
        </button>
      </div>

      {/* Progress as a shape, not only a sentence. */}
      <div className="mt-6 flex gap-1.5" aria-hidden>
        {progressSegments(steps).map((filled, index) => (
          <div
            key={index}
            className={`h-1.5 flex-1 rounded-full ${filled ? "bg-accent" : "bg-well"}`}
          />
        ))}
      </div>

      <ol className="mt-6 space-y-3">
        {steps.map((step, index) => {
          const isNext = step.id === nextId;
          return (
            <li
              key={step.id}
              // A grid, not a wrapping flex row: with flex the button stays on
              // the text's line at phone width and squeezes it to a word a line.
              className={`grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 rounded-lg border px-4 py-4 sm:grid-cols-[auto_1fr_auto] ${
                isNext ? "border-accent-line bg-accent-wash" : "border-hair"
              }`}
            >
              <span
                aria-hidden
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] ${
                  step.done ? "bg-accent text-ground" : "border border-hair-strong text-muted"
                }`}
              >
                {step.done ? "✓" : index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className={`text-sm font-medium ${step.done ? "text-muted" : "text-ink"}`}>
                  {step.label}
                  <span className="sr-only">{step.done ? " (done)" : " (not done)"}</span>
                </p>
                <p className="mt-1 text-sm leading-relaxed text-muted">
                  {step.done && step.detail ? step.detail : step.body}
                </p>
              </div>
              <button
                type="button"
                onClick={() => onSelectTab(step.id)}
                className={`col-start-2 justify-self-start self-start sm:col-start-3 ${buttonClass(
                  isNext ? "primary" : "secondary",
                  "sm",
                )}`}
              >
                {step.cta}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** The collapsed checklist: what is left, as links, on one line.
 *
 *  Real `?tab=` links, so a step can be opened in a new tab; a plain click
 *  goes through `onSelectTab`, which keeps the dashboard's other params the
 *  way the section nav does. */
function SetupBanner({
  steps,
  onSelectTab,
  onHide,
}: {
  steps: Step[];
  onSelectTab: (tab: StepTab) => void;
  onHide: () => void;
}) {
  const pending = steps.filter((step) => !step.done);
  return (
    <section
      aria-label="Finish setting up"
      className="mb-8 flex min-h-12 items-center gap-3 rounded-xl border border-hair bg-surface py-2 pl-4 pr-2 shadow-[var(--cf-shadow-card)]"
    >
      <p className="min-w-0 flex-1 text-sm text-muted">
        <span className="font-medium text-ink">{stepsLeftLabel(steps)}:</span>{" "}
        {pending.map((step, index) => (
          <span key={step.id}>
            {index > 0 ? <span aria-hidden className="text-faint"> · </span> : null}
            <a
              href={`?tab=${step.id}`}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                event.preventDefault();
                onSelectTab(step.id);
              }}
              className="font-medium text-accent underline-offset-2 hover:underline"
            >
              {step.cta}
            </a>
          </span>
        ))}
      </p>
      <button
        type="button"
        onClick={onHide}
        aria-label="Dismiss setup reminder"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-lg leading-none text-muted transition-colors hover:bg-well hover:text-ink"
      >
        <span aria-hidden>×</span>
      </button>
    </section>
  );
}

/** The line under the heading. It has to agree with the steps. Only the full
 *  card has one, and the full card only shows before anything is issued — an
 *  org that has issued gets the banner instead. */
function summary(steps: Step[], orgName: string): string {
  const lookDone = steps.filter((step) => step.id !== "issue").every((step) => step.done);
  if (lookDone) {
    return "Your design is ready. Issue a credential to see it on a real document.";
  }
  return `You can issue a credential right now on the standard design. The other steps make it look like it came from ${orgName}.`;
}

// Per org and per browser: hiding is a viewing preference, not org state, so
// it does not belong in the API. Storage can throw (private mode, blocked
// site data); the checklist then simply shows, which is the safe default.
const noSubscription = () => () => {};

const hiddenKey = (slug: string) => `certforge:setup-checklist-hidden:${slug}`;

function readHidden(slug: string): boolean {
  try {
    return window.localStorage.getItem(hiddenKey(slug)) === "1";
  } catch {
    return false;
  }
}

function writeHidden(slug: string): void {
  try {
    window.localStorage.setItem(hiddenKey(slug), "1");
  } catch {
    // Hidden for this visit only.
  }
}
