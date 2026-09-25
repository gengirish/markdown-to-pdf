import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildSteps,
  checklistMode,
  nextStep,
  orderSteps,
  progressSegments,
  stepsLeftLabel,
} from "./setup-steps.ts";

type Branding = Parameters<typeof buildSteps>[0];

const unbranded: Branding = { logo_asset_id: null, primary_color: null, accent_color: null, footer_text: null };
const branded: Branding = { ...unbranded, primary_color: "#0E6B58" };

function checklist(org: Branding, templates: number, credentials: number) {
  return orderSteps(buildSteps(org, { templates, credentials }));
}

test("0 done: no segment filled, definition order, branding is next", () => {
  const steps = checklist(unbranded, 0, 0);
  assert.deepEqual(progressSegments(steps), [false, false, false]);
  assert.deepEqual(steps.map((s) => s.id), ["branding", "templates", "issue"]);
  assert.equal(nextStep(steps)?.id, "branding");
});

// The reported bug: only step three done lit the *third* segment and
// half-lit the first.
test("1 done (issue only): first segment filled, done step moves to the top", () => {
  const steps = checklist(unbranded, 0, 4);
  assert.deepEqual(progressSegments(steps), [true, false, false]);
  assert.deepEqual(steps.map((s) => s.id), ["issue", "branding", "templates"]);
  assert.equal(nextStep(steps)?.id, "branding");
});

test("2 done: two segments filled, the one pending step is next and last", () => {
  const steps = checklist(branded, 0, 4);
  assert.deepEqual(progressSegments(steps), [true, true, false]);
  assert.deepEqual(steps.map((s) => s.id), ["branding", "issue", "templates"]);
  assert.equal(nextStep(steps)?.id, "templates");
});

test("3 done: every segment filled, nothing next", () => {
  const steps = checklist(branded, 2, 4);
  assert.deepEqual(progressSegments(steps), [true, true, true]);
  assert.equal(nextStep(steps), undefined);
});

test("every 1-done combination fills the first segment only", () => {
  for (const steps of [checklist(branded, 0, 0), checklist(unbranded, 1, 0), checklist(unbranded, 0, 1)]) {
    assert.deepEqual(progressSegments(steps), [true, false, false]);
    assert.equal(steps[0].done, true);
  }
});

test("mode: full card until a credential is issued, however much else is done", () => {
  assert.equal(checklistMode(checklist(unbranded, 0, 0)), "card");
  assert.equal(checklistMode(checklist(branded, 0, 0)), "card");
  assert.equal(checklistMode(checklist(branded, 3, 0)), "card");
});

test("mode: one-line banner once anything is issued, complete when all done", () => {
  assert.equal(checklistMode(checklist(unbranded, 0, 1)), "banner");
  assert.equal(checklistMode(checklist(branded, 0, 1)), "banner");
  assert.equal(checklistMode(checklist(branded, 1, 1)), "complete");
});

test("banner label counts the pending steps", () => {
  assert.equal(stepsLeftLabel(checklist(unbranded, 0, 1)), "2 steps left");
  assert.equal(stepsLeftLabel(checklist(branded, 0, 1)), "1 step left");
});
