import { test } from "node:test";
import assert from "node:assert/strict";

import { looksAutoNamed } from "./org-name.ts";

test("the generated names are recognised, whatever the apostrophe or case", () => {
  for (const name of ["Priya's Organization", "GS IT’s Organization", "ada's organization  "]) {
    assert.equal(looksAutoNamed(name), true, name);
  }
});

test("names a person chose are left alone", () => {
  for (const name of ["Acme Organization", "IntelliForge", "Organization", "'s Organization", "Priya's Organizations"]) {
    assert.equal(looksAutoNamed(name), false, name);
  }
});
