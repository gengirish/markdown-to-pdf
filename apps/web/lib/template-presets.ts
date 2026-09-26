import type { TemplateConfig } from "./api";

/** What each guided "Base layout" says by default, and how switching layouts
 *  carries the wording with it.
 *
 *  The layout select used to change only `layout`: choosing Appreciation left
 *  the heading reading CERTIFICATE OF PARTICIPATION, and the author had to know
 *  to retype three fields. Now a switch swaps in the new layout's wording — but
 *  only into fields still holding *some* layout's stock text. Anything the
 *  author wrote themselves is theirs and stays.
 *
 *  Participation's wording matches DEFAULT_CONFIG in
 *  apps/api/api/services/templates.py. Imports are type-only so `node --test`
 *  can load this file.
 */

type Layout = TemplateConfig["layout"];
type Wording = Pick<TemplateConfig, "heading" | "body" | "closing">;

export const LAYOUT_WORDING: Record<Layout, Wording> = {
  participation: {
    heading: "CERTIFICATE OF PARTICIPATION",
    body: "This is to certify that",
    closing: "has successfully participated in",
  },
  internship: {
    heading: "CERTIFICATE OF INTERNSHIP",
    body: "This is to certify that",
    closing: "has successfully completed an internship in",
  },
  appreciation: {
    heading: "CERTIFICATE OF APPRECIATION",
    body: "This certificate is proudly presented to",
    closing: "in appreciation of their contribution to",
  },
};

const WORDING_KEYS = ["heading", "body", "closing"] as const;

/** A field is "stock" when it is empty or matches any layout's default. */
function isStock(key: (typeof WORDING_KEYS)[number], value: string): boolean {
  const trimmed = value.trim();
  return (
    trimmed === "" ||
    Object.values(LAYOUT_WORDING).some((wording) => wording[key] === trimmed)
  );
}

export function switchLayout(config: TemplateConfig, layout: Layout): TemplateConfig {
  const next: TemplateConfig = { ...config, layout };
  for (const key of WORDING_KEYS) {
    if (isStock(key, config[key])) next[key] = LAYOUT_WORDING[layout][key];
  }
  return next;
}
