import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/** The palette's text pairings, measured from app/globals.css itself.
 *
 *  apps/web/CLAUDE.md says contrast is measured, not eyeballed; this is the
 *  measurement, kept. Every pair below is one the dashboard actually renders
 *  as small text, so each must clear WCAG AA's 4.5:1 in both themes. Changing
 *  a token that breaks one fails here rather than in someone's eyes.
 */

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

/** The block that `selector {` opens. Anchored on the brace because the
 *  selectors also appear in globals.css's comments, and a match there reads
 *  whichever block happens to come next. */
function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `no ${selector} block`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/--cf-([a-z-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2].toLowerCase()]),
  );
}

const light = tokens(":root");
const dark = tokens(':root[data-theme="dark"]');
const darkBySystem = tokens(":root:not([data-theme])");

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground, background, where it appears]
const PAIRS: [string, string, string][] = [
  ["ink", "surface", "body text"],
  ["muted", "surface", "helper text"],
  ["faint", "surface", "secondary helper text"],
  ["faint", "ground", "helper text on the page background"],
  ["placeholder", "surface", "input placeholders"],
  ["accent", "surface", "eyebrows, links"],
  ["accent", "accent-wash", "the next-step highlight, the setup banner's links"],
  ["muted", "well", "disabled buttons, wizard step numbers"],
  ["ground", "accent", "primary button label"],
  ["ground", "danger", "the revoke button label"],
  ["danger", "surface", "error text"],
  ["warn-ink", "warn-wash", "warning notes"],
];

for (const [theme, palette] of [["light", light], ["dark", dark]] as const) {
  for (const [fg, bg, where] of PAIRS) {
    test(`${theme}: ${fg} on ${bg} (${where}) clears 4.5:1`, () => {
      assert.ok(palette[fg] && palette[bg], `missing token ${fg} or ${bg}`);
      const measured = ratio(palette[fg], palette[bg]);
      assert.ok(measured >= 4.5, `${fg} ${palette[fg]} on ${bg} ${palette[bg]} is ${measured.toFixed(2)}:1`);
    });
  }
}

// The dark palette is written twice (the explicit toggle, and the OS
// preference for a visitor with no toggle set); CLAUDE.md says they must not
// drift. A value fixed in one block and not the other passes every check
// above and still ships the old colour to half the dark-mode visitors.
test("the two dark-mode blocks define identical colours", () => {
  assert.deepEqual(darkBySystem, dark);
});
