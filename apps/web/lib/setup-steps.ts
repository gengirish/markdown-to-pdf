import type { OrgProfile } from "./api";

/** The setup checklist's logic, with no React in it.
 *
 *  Split out of `components/dashboard/setup-checklist.tsx` so it can be tested
 *  under plain `node --test`: this app has no component test runner, and the
 *  part worth pinning is the ordering, not the markup. Keep the imports
 *  type-only — Node strips types, it does not resolve `@/` aliases.
 */

export type StepTab = "branding" | "templates" | "issue";

export interface Step {
  id: StepTab;
  label: string;
  body: string;
  done: boolean;
  detail: string | null;
  cta: string;
}

export interface Counts {
  templates: number;
  credentials: number;
}

export function buildSteps(
  org: Pick<OrgProfile, "logo_asset_id" | "primary_color" | "accent_color" | "footer_text">,
  counts: Counts,
): Step[] {
  // Only what reaches the certificate counts as branding. `logo_url` is an
  // external address the PDF renderer refuses to fetch, so an org that set
  // only that has changed its public page, not its documents.
  const branded = Boolean(
    org.logo_asset_id || org.primary_color || org.accent_color || org.footer_text,
  );
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

  return [
    {
      id: "branding",
      label: "Add your logo and colours",
      body: "Upload a logo and set your colours. They print on every certificate and show on the public verify page.",
      done: branded,
      detail: org.logo_asset_id ? "Logo uploaded." : "Colours set. A logo would print on every certificate too.",
      cta: branded ? "Edit branding" : "Add branding",
    },
    {
      id: "templates",
      label: "Choose a certificate design",
      body: "Start from a ready-made design, build one with the guided form, or upload your own artwork and place the fields on it.",
      done: counts.templates > 0,
      detail: `${plural(counts.templates, "template")} in your library.`,
      cta: counts.templates > 0 ? "View templates" : "Choose a design",
    },
    {
      id: "issue",
      label: "Issue your first credential",
      body: "Issue one to a single person, or upload a CSV for a whole cohort. Each gets a verify link, a PDF and an Open Badge.",
      done: counts.credentials > 0,
      detail: `${plural(counts.credentials, "credential")} issued.`,
      cta: counts.credentials > 0 ? "Issue more" : "Issue a credential",
    },
  ];
}

/** Done steps first, then pending, each group in its original order.
 *
 *  Issuing is step three but the step people most often do first, so in
 *  definition order a "1 of 3 done" list ticked its last row and the bar
 *  filled from the right. Sorting puts the ticks where the eye expects
 *  progress to start. */
export function orderSteps(steps: Step[]): Step[] {
  return [...steps.filter((step) => step.done), ...steps.filter((step) => !step.done)];
}

/** One boolean per bar segment, filled left to right by the *count* done —
 *  never by which step it was. */
export function progressSegments(steps: Step[]): boolean[] {
  const done = steps.filter((step) => step.done).length;
  return steps.map((_, index) => index < done);
}

/** The first pending step, which the checklist highlights. */
export function nextStep(steps: Step[]): Step | undefined {
  return steps.find((step) => !step.done);
}
