import { test } from "node:test";
import assert from "node:assert/strict";

import type { TemplateSummary } from "./api";
import { defaultTemplateFor } from "./template-default.ts";

function tpl(id: string, name: string, is_default: boolean): TemplateSummary {
  return { id, name, is_default, variables: [], is_guided: true, created_at: null, updated_at: null, background_asset_id: null };
}

test("the org's own default wins over the global one", () => {
  const own = [tpl("o1", "Workshop", false), tpl("o2", "Internship", true)];
  const global = [tpl("g1", "Classic", true)];
  assert.equal(defaultTemplateFor(own, global)?.id, "o2");
});

test("with no own default, the global default is used", () => {
  assert.equal(defaultTemplateFor([tpl("o1", "Workshop", false)], [tpl("g1", "Classic", true)])?.id, "g1");
});

test("several defaults resolve to the first by name, as the SQL orders them", () => {
  const own = [tpl("z", "Zeta", true), tpl("a", "Alpha", true)];
  assert.equal(defaultTemplateFor(own, [])?.id, "a");
});

test("nothing marked default means no default", () => {
  assert.equal(defaultTemplateFor([tpl("o1", "Workshop", false)], []), undefined);
});
