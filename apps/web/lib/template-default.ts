import type { TemplateSummary } from "./api";

/** The template the API renders with when no template_id is sent.
 *
 *  A mirror of `resolve_template_id` in apps/api/api/services/issuance.py:
 *  the org's own default first, then the global default, each the first by
 *  name. The dashboard labels "Organization default — {name}" and previews it
 *  from this, so if the two rules drift the form names one design and the
 *  credential issues on another. Type-only imports, so `node --test` runs it.
 */
export function defaultTemplateFor(
  own: TemplateSummary[],
  global: TemplateSummary[],
): TemplateSummary | undefined {
  const firstDefault = (list: TemplateSummary[]) =>
    [...list].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)).find((tpl) => tpl.is_default);
  return firstDefault(own) ?? firstDefault(global);
}
