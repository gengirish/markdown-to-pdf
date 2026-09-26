import type { OrgProfile } from "./api";

/** The branding form's fields, and how they follow the org without eating edits.
 *
 *  The form has two save models side by side: the logo uploads the moment it is
 *  picked, and the colours and footer wait for "Save branding". Uploading a logo
 *  refetches the org, and the form used to re-prefill every field from whatever
 *  arrived — so a colour picked but not yet saved was reset by the upload. A beta
 *  user reported exactly that.
 *
 *  The rule now: a field follows the org only while it still holds the value the
 *  org last had. Once someone has typed in it, an incoming org leaves it alone.
 *  Kept free of React so `node --test` can pin it. Imports are type-only.
 */

export interface BrandingFields {
  primaryColor: string;
  accentColor: string;
  footerText: string;
  logoUrl: string;
}

/** Empty strings rather than the API's nulls: a controlled input cannot hold null. */
export function fieldsFromOrg(
  org: Pick<OrgProfile, "primary_color" | "accent_color" | "footer_text" | "logo_url">,
): BrandingFields {
  return {
    primaryColor: org.primary_color ?? "",
    accentColor: org.accent_color ?? "",
    footerText: org.footer_text ?? "",
    logoUrl: org.logo_url ?? "",
  };
}

/** What the form shows after the org changes underneath it.
 *
 *  `baseline` is what the org held the last time the form followed it (null
 *  before the first load). A field equal to its baseline is untouched and takes
 *  the incoming value; anything else is an edit and is kept. */
export function followOrg(
  current: BrandingFields,
  baseline: BrandingFields | null,
  incoming: BrandingFields,
): BrandingFields {
  if (baseline === null) return incoming;
  const pick = (key: keyof BrandingFields) =>
    current[key] === baseline[key] ? incoming[key] : current[key];
  return {
    primaryColor: pick("primaryColor"),
    accentColor: pick("accentColor"),
    footerText: pick("footerText"),
    logoUrl: pick("logoUrl"),
  };
}

/** Whether the form holds anything "Save branding" would change. */
export function isDirty(current: BrandingFields, baseline: BrandingFields | null): boolean {
  if (baseline === null) return false;
  return (Object.keys(current) as (keyof BrandingFields)[]).some(
    (key) => current[key] !== baseline[key],
  );
}
