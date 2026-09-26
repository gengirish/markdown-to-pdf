import { test } from "node:test";
import assert from "node:assert/strict";

import type { TemplateConfig } from "./api.ts";
import { LAYOUT_WORDING, switchLayout } from "./template-presets.ts";

const participation: TemplateConfig = {
  layout: "participation",
  ...LAYOUT_WORDING.participation,
  signature_name: "",
  signature_title: "",
  show_qr: true,
  show_logo: true,
  show_footer: true,
};

// The reported gap: picking Appreciation left the heading on Participation.
test("switching layout brings that layout's heading with it", () => {
  const next = switchLayout(participation, "appreciation");
  assert.equal(next.layout, "appreciation");
  assert.equal(next.heading, "CERTIFICATE OF APPRECIATION");
  assert.equal(next.closing, LAYOUT_WORDING.appreciation.closing);
});

test("text the author wrote is never overwritten", () => {
  const custom = { ...participation, heading: "HACKATHON WINNER" };
  const next = switchLayout(custom, "internship");
  assert.equal(next.heading, "HACKATHON WINNER");
  assert.equal(next.closing, LAYOUT_WORDING.internship.closing);
});

test("a cleared field takes the new default", () => {
  const next = switchLayout({ ...participation, body: "  " }, "appreciation");
  assert.equal(next.body, LAYOUT_WORDING.appreciation.body);
});

test("round-tripping through layouts lands back on the original wording", () => {
  const there = switchLayout(participation, "internship");
  assert.deepEqual(switchLayout(there, "participation"), participation);
});

test("everything but the wording is left alone", () => {
  const signed = { ...participation, signature_name: "A. Rao", show_qr: false };
  const next = switchLayout(signed, "appreciation");
  assert.equal(next.signature_name, "A. Rao");
  assert.equal(next.show_qr, false);
});
