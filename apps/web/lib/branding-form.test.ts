import { test } from "node:test";
import assert from "node:assert/strict";

import { fieldsFromOrg, followOrg, isDirty } from "./branding-form.ts";

const saved = fieldsFromOrg({
  primary_color: null,
  accent_color: null,
  footer_text: "Old footer",
  logo_url: null,
});

// The reported bug: pick colours, upload a logo, colours reset. The upload
// refetches the org, which still has the *saved* colours.
test("an org refetch keeps colours picked but not saved", () => {
  const edited = { ...saved, primaryColor: "#112233", accentColor: "#445566" };
  const afterUpload = followOrg(edited, saved, saved);
  assert.equal(afterUpload.primaryColor, "#112233");
  assert.equal(afterUpload.accentColor, "#445566");
});

test("an untouched field follows the org", () => {
  const incoming = { ...saved, footerText: "New footer" };
  assert.equal(followOrg(saved, saved, incoming).footerText, "New footer");
});

test("the first load takes everything from the org", () => {
  const blank = fieldsFromOrg({ primary_color: null, accent_color: null, footer_text: null, logo_url: null });
  assert.deepEqual(followOrg(blank, null, saved), saved);
});

test("after a save the form matches the org and is clean", () => {
  const edited = { ...saved, primaryColor: "#112233" };
  const stored = { ...saved, primaryColor: "#112233" };
  const next = followOrg(edited, saved, stored);
  assert.deepEqual(next, stored);
  assert.equal(isDirty(next, stored), false);
});

test("dirty tracks an edit and clears when it is undone", () => {
  assert.equal(isDirty({ ...saved, footerText: "x" }, saved), true);
  assert.equal(isDirty(saved, saved), false);
  assert.equal(isDirty(saved, null), false);
});
