# TODO · The organization logo can never render in a certificate PDF

**Opened** 2026-09-03 · **Status** OPEN · **Trigger** beta-user feedback (Gouthami,
Xeroura Technologies) — "i have added our company logo as well, i was expecting the
logo of the company and formatting to be aligned"

## The finding

The guided template form has an **Organization logo** checkbox. Ticking it is
inert: the logo cannot appear in a rendered PDF, under any configuration, for
any org. Nothing reports an error at any stage.

The chain, each link correct on its own:

1. `apps/web/components/dashboard/branding-card.tsx` takes a logo **URL** as a
   text field and saves it to `organizations.logo_url`.
2. `api/services/templates.py` `build_html_from_config()` emits, when
   `show_logo` is set:

   ```html
   <img src="{{logo_url}}" height="30" />
   ```

3. `api/services/rendering.py` `build_render_variables()` resolves that
   placeholder to `org.logo_url or ""` — the external `https://…` string,
   verbatim.
4. `api/core/pdf_renderer.py` `_pdf_link_callback()` returns `_BLOCKED` for any
   URI containing `://`:

   > `http(s) and friends: never fetch on a template author's behalf.`

So xhtml2pdf is handed a path that does not exist, and per that function's own
docstring "the element simply does not render".

### Reproducing it

```
POST /api/v1/orgs/{slug}          {"logoUrl": "https://example.com/logo.png"}
POST /api/v1/orgs/{slug}/templates  {"config": {"show_logo": true}}
POST /api/v1/orgs/{slug}/templates/preview
```

The returned PDF contains no logo. The same request with `show_logo: false`
returns a PDF that differs only by the empty table row.

## Why it matters

It is the single most requested branding feature, and it is the first thing a
new organization tries — the checkbox is on by default (`DEFAULT_CONFIG`
line 148, `"show_logo": True`). Every certificate any org has issued through a
guided template has silently dropped its logo.

Worse than dropping it: the UI **claims** it. A checkbox that is checked is a
statement that the logo is on the certificate. This is the same class of defect
as `template-preview-lied-about-the-render.md` and
`email-delivery-observability.md` — the product reporting an outcome it did not
produce.

## What it does *not* affect

- **The viewer page.** `routes/verify.py` renders `org.logo_url` in an `<img>`
  through `safe_public_url()`, and a browser fetches it normally. Her scan
  screenshot shows the header logo slot working. This is a PDF-only defect,
  which is part of why it went unnoticed.
- **`badge.json`.** The Open Badges `issuer.image` carries the URL, and a badge
  consumer dereferences it itself.
- **Traced templates.** Those carry the customer's own artwork, logo included,
  as `{{background}}` — a data URI. They are the proof the fix works.
- **The seeded default templates.** None has a logo slot at all, so they were
  never affected. `CLAUDE.md` already said `logo_url` "is passed through but
  none of them has a layout slot for it yet" — true, and it is what hid this:
  the guided *generator* does have a slot.

## Fix options

### A. Fetch and re-encode to a data URI, memoised by checksum — recommended

Exactly what `api/services/backgrounds.py` already does for template artwork.
`logo_url` becomes a data URI in `build_render_variables()`, so the renderer
never fetches anything and `_pdf_link_callback` keeps refusing everything.

The cost is that the *server* now fetches a customer-supplied URL, which is an
SSRF surface the background path never had — an uploaded asset arrives as bytes
on a request the org authenticated. So this needs, and none of it is optional:

- an allowlist of schemes (`https:` only) and a block on private/link-local
  address ranges, resolved **after** DNS and re-checked on every redirect hop;
- a response size cap and a short timeout;
- decode-and-re-encode through Pillow, the same `_reencode` discipline
  `routes/templates.py` applies to uploads, so nothing but pixels survives;
- a failure that renders no logo rather than failing the issuance — a
  credential must not become un-issuable because a customer's CDN is down.

### B. Upload the logo as a `TemplateAsset` instead of naming a URL

Reuses the whole existing path — R2, `_reencode`, checksum memoisation — and
introduces no fetcher at all. Strictly safer, and it makes the logo consistent
with how artwork already works. The cost is a dashboard change (a file input,
not a text field) and a migration story for orgs that already set a URL, whose
value would keep working for the viewer while the PDF reads the asset.

### C. Remove the checkbox

Honest, and cheap. But the feature is wanted, so this only converts a silent
failure into a missing feature.

**Recommendation: B, then A only if customers ask to keep naming a URL.** B
adds no new attack surface and reuses code already carrying the security
review. A exists in this list mainly because the URL field is what the
dashboard ships today.

## Why the existing tests missed it

Three tests mention a logo and none could have caught this:

- `test_templates.py:81` asserts `<img src="{{logo_url}}">` is *accepted* by
  `validate_template_html`. It is — that is the placeholder rule working.
- `test_verify_viewer.py:351` and `:383` cover the logo on the **viewer**,
  where it genuinely renders, and its `javascript:` scheme check.
- `test_organizations.py:9` asserts the column round-trips.

Every one tests one side of the join. Nothing renders a PDF for an org that has
a logo and asks whether the image is in the bytes — and per the note already in
`CLAUDE.md`, "a PDF containing an image is not evidence" on its own, because the
QR code is an image too. The guard has to be the same one the traced-background
test uses: render with and without the logo and compare the two documents.

Add that test **before** the fix, and watch it fail.
