"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { toApiError, type OrgProfile } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { Card, ErrorNote } from "./ui";

/** A colour the API will accept back. The server stores whatever it is given,
 *  so the check is here: a malformed value would reach a PDF template and
 *  render as a broken style rather than an error anyone sees. */
const HEX = /^#[0-9a-fA-F]{6}$/;

/** Only what the credential PDF actually uses. `name` is edited through Clerk,
 *  which owns the organization record, so it is deliberately not here — two
 *  places to rename an org is how the two get out of step. */
export function BrandingCard({
  slug,
  org,
  onSaved,
}: {
  slug: string;
  org: OrgProfile | null;
  onSaved: (updated: OrgProfile) => void;
}) {
  const api = useCertForge();

  const [primaryColor, setPrimaryColor] = useState("");
  const [accentColor, setAccentColor] = useState("");
  const [footerText, setFooterText] = useState("");
  const [logoUrl, setLogoUrl] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Prefilled from the org once it loads. Empty string rather than the API's
  // null, because a controlled input cannot hold null without React warning
  // about switching between controlled and uncontrolled.
  useEffect(() => {
    if (!org) return;
    setPrimaryColor(org.primary_color ?? "");
    setAccentColor(org.accent_color ?? "");
    setFooterText(org.footer_text ?? "");
    setLogoUrl(org.logo_url ?? "");
  }, [org]);

  const invalidPrimary = primaryColor !== "" && !HEX.test(primaryColor);
  const invalidAccent = accentColor !== "" && !HEX.test(accentColor);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      // An emptied field is sent as null, not omitted. Omitting it would mean
      // "leave it alone", so clearing a colour would silently do nothing.
      const updated = await api.updateOrg(slug, {
        primaryColor: primaryColor || null,
        accentColor: accentColor || null,
        footerText: footerText || null,
        logoUrl: logoUrl || null,
      });
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setSaving(false);
    }
  }, [api, slug, primaryColor, accentColor, footerText, logoUrl, onSaved]);

  const blocked = saving || invalidPrimary || invalidAccent;

  return (
    <Card
      title="Certificate branding"
      description="Applied when a credential PDF is rendered. Existing credentials pick this up the next time they are downloaded."
    >
      {org === null ? (
        <ErrorNote>Branding cannot load until the organization does.</ErrorNote>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ColorField
              label="Primary colour"
              value={primaryColor}
              onChange={setPrimaryColor}
              invalid={invalidPrimary}
            />
            <ColorField
              label="Accent colour"
              value={accentColor}
              onChange={setAccentColor}
              invalid={invalidAccent}
            />

            <label className="block sm:col-span-2">
              <span className="mb-2 block text-sm font-medium text-ink">Footer line</span>
              <input
                type="text"
                value={footerText}
                placeholder="Printed at the foot of every certificate"
                onChange={(event) => setFooterText(event.target.value)}
                className="w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink focus:border-accent focus:outline-none"
              />
            </label>
          </div>

          <p className="mt-4 text-xs text-faint">
            Leave a field empty to fall back to the default branding.
          </p>

          <LogoField slug={slug} org={org} onChanged={onSaved} legacyUrl={logoUrl} />

          <div className="mt-6 flex items-center justify-end gap-4">
            {saved ? <span className="text-sm text-accent">Saved</span> : null}
            <button
              onClick={save}
              disabled={blocked}
              className="rounded-lg bg-accent px-6 py-3 font-medium text-ground transition-colors hover:bg-accent-hover disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save branding"}
            </button>
          </div>

          {error ? (
            <div className="mt-6">
              <ErrorNote>{error}</ErrorNote>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function ColorField({
  label,
  value,
  onChange,
  invalid,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  invalid: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-ink">{label}</span>
      <div className="flex items-center gap-3">
        {/* A native swatch alongside the text field, so a colour can be picked
            or typed. It needs a valid value at all times, so it falls back to a
            neutral while the text field is empty or mid-edit. */}
        <input
          type="color"
          aria-label={`${label} swatch`}
          value={HEX.test(value) ? value : "#3f3f46"}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 w-12 shrink-0 cursor-pointer rounded-lg border border-hair bg-surface p-1"
        />
        <input
          type="text"
          value={value}
          placeholder="#4f46e5"
          spellCheck={false}
          onChange={(event) => onChange(event.target.value.trim())}
          aria-invalid={invalid}
          className={`w-full rounded-lg border bg-surface px-4 py-2.5 font-mono text-sm text-ink focus:outline-none ${
            invalid
              ? "border-warn focus:border-warn"
              : "border-hair focus:border-accent"
          }`}
        />
      </div>
      {invalid ? (
        <span className="mt-1.5 block text-xs text-warn-ink">
          Use a six-digit hex colour, like #4f46e5.
        </span>
      ) : null}
    </label>
  );
}

/** The logo, uploaded rather than linked.
 *
 *  A URL cannot work here and never could: the PDF renderer refuses to fetch
 *  anything — that refusal is what stops a template author turning a render
 *  into a server-side request — so `<img src="https://…">` in a certificate
 *  resolved to nothing, silently, for every organization that set one. The
 *  bytes have to be ours. See docs/TODOs/org-logo-never-renders-in-a-pdf.md.
 *
 *  Uploading applies immediately rather than on "Save branding". It is a file
 *  transfer, not a form field, and a button that saves a picture and four
 *  colours together has to explain which half failed when one of them does.
 */
function LogoField({
  slug,
  org,
  onChanged,
  legacyUrl,
}: {
  slug: string;
  org: OrgProfile;
  onChanged: (updated: OrgProfile) => void;
  legacyUrl: string;
}) {
  const api = useCertForge();
  const input = useRef<HTMLInputElement>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uploaded = org.logo_asset_id !== null;

  // Cache-busted on the asset id: the URL is per-org and stable, so replacing
  // the logo would otherwise keep showing the old one until the browser's copy
  // expired. The id changes with the bytes, which is exactly the right key.
  const preview = uploaded
    ? `${api.orgLogoUrl(slug)}?v=${org.logo_asset_id}`
    : null;

  const run = useCallback(
    async (work: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await work();
        // The upload and the delete both return the asset, not the org, so the
        // org is refetched rather than patched locally — one source of truth
        // for what is actually stored.
        onChanged(await api.getOrg(slug));
      } catch (err) {
        setError(toApiError(err).message);
      } finally {
        setBusy(false);
      }
    },
    [api, slug, onChanged],
  );

  const onPick = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      // Clearing the input is what lets the same file be picked twice after a
      // failed attempt; without it the change event never fires again.
      event.target.value = "";
      if (file) void run(() => api.uploadOrgLogo(slug, file));
    },
    [api, slug, run],
  );

  return (
    <div className="mt-6 border-t border-hair-soft pt-6">
      <span className="mb-2 block text-sm font-medium text-ink">Logo</span>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex h-16 w-32 shrink-0 items-center justify-center rounded-lg border border-hair bg-sunken p-2">
          {preview ? (
            /* A public API URL on another host, not an asset next/image can
               optimise — and the whole point is to show the exact bytes the
               certificate embeds. */
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={preview}
              alt="Organization logo"
              className="max-h-full max-w-full object-contain"
            />
          ) : (
            <span className="text-xs text-placeholder">No logo</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={onPick}
            className="hidden"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => input.current?.click()}
            className="rounded-lg border border-hair px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-accent disabled:opacity-50"
          >
            {busy ? "Working…" : uploaded ? "Replace" : "Upload a logo"}
          </button>

          {uploaded ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(() => api.removeOrgLogo(slug))}
              className="rounded-lg px-3 py-2 text-sm text-faint transition-colors hover:text-danger disabled:opacity-50"
            >
              Remove
            </button>
          ) : null}
        </div>
      </div>

      <p className="mt-3 text-xs text-faint">
        PNG, JPEG or WebP. Transparency is preserved. Applies to certificates
        rendered from here on — a credential already issued picks it up the next
        time its PDF is downloaded.
      </p>

      {/* Only shown to the orgs that have one, because for everyone else it
          describes a field that is no longer in this form. Saying nothing would
          leave them with a logo on the verification page, none on the
          certificate, and no explanation for the difference. */}
      {legacyUrl && !uploaded ? (
        <p className="mt-2 text-xs text-warn-ink">
          This organization has a logo URL set. It appears on the public
          verification page, but it cannot be printed on a certificate — the PDF
          renderer does not fetch external images. Upload the file to put it on
          the document.
        </p>
      ) : null}

      {error ? (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}
    </div>
  );
}
