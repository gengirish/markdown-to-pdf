# TODO · The template preview did not render what issuance renders

**Opened** 2026-08-31 · **Status** CLOSED — fixed and covered by tests 2026-08-31
· **Trigger** a pass over the template preview feature end to end

## The finding

`POST /api/v1/orgs/{slug}/templates/preview` exists so a template author can see
their certificate before issuing one. It built its variables in its own place —
`sample_variables()` in `api/services/templates.py`, a hand-written dict — while
every real render builds them in `build_render_variables()`, which
`api/services/rendering.py` documents as "the one implementation".

Two producers of one vocabulary. They had already drifted:

```
$ python -c "from api.services.templates import sample_variables, BUILTIN_VARIABLES; \
             print(sorted(BUILTIN_VARIABLES - set(sample_variables())))"
['display_font', 'font_face']
```

Both names are emitted into **every** template the guided generator produces
(`build_html_from_config`, `templates.py:654,658,682`). `render_credential_pdf`
blanks any placeholder it has no value for, so in a preview `{{font_face}}`
became nothing and `font-family:{{display_font}}` became `font-family:;`.

**Every guided preview was rendered in the renderer's default face, and every
credential issued from that same template in EB Garamond.** No error, no warning,
no visible placeholder — the author approved a PDF that differed from the one the
recipient gets, in the one property a preview is read for.

A second, smaller instance of the same shape: the route copied four branding
fields (`issuer_name`, `logo_url`, `primary_color`, `accent_color`) from the org
onto the sample dict by hand. A copy list is a third enumeration of the org's
branding, so `footer_text` — supplied by `build_render_variables`, absent from
the copy list — previewed as the sample string and issued as the org's.

## The other half: the button that did nothing

`templates-card.tsx` fetched the PDF and then called `window.open`. By that point
the click's user gesture is spent, and Safari and Firefox block a popup opened
outside one **by default**. A blocked popup is not a rejected promise, so the
`catch` never ran: the button spun, cleared, and produced nothing at all — no
tab, no error, no way to tell it apart from a slow render.

## What it costs

- A preview that is wrong is worse than no preview, because it is trusted. The
  font divergence is invisible at every stage before the recipient's copy.
- The popup failure made the whole feature look broken to anyone not on Chrome,
  with nothing in the UI or the API logs to say so.
- Nothing here is frozen, and no issued credential was rendered wrongly — the
  drift was in the preview's direction only.

## The fix

- `sample_variables(org, background)` now calls `build_render_variables()` with a
  stand-in `Credential` and the caller's real `Organization`. There is one
  producer again, so the vocabulary cannot drift. Two divergences are kept on
  purpose and documented in the function: the recipient is fictional, and the
  footer says "Preview — not a real credential", so a forwarded preview cannot
  be read as a credential.
- The preview route passes the org whole instead of copying four keys, and
  resolves the artwork data URI for a traced template.
- The dashboard opens the tab synchronously inside the click and navigates it
  when the PDF arrives, closing it if the render fails. `noopener` cannot be
  passed to `window.open` there — per spec it returns null, and the handle is
  the point — so `tab.opener` is cleared instead. If the popup is blocked
  anyway, the PDF downloads.

## Why the tests missed it

`test_preview_returns_a_pdf_without_saving_anything` asserted a 200, a PDF
content type, and that no row was written. All three were true throughout. The
suite had no assertion relating the preview to the render at all, and a font that
silently falls back does not change the status code, the byte signature, or the
page count.

`test_every_builtin_variable_is_actually_produced` (JOIN 1) covered exactly this
class — for the *other* producer. It was written against
`build_render_variables` and never asked whether anything else claimed to supply
the same names.

Three guards added in `tests/test_template_assets.py`, each verified by
reintroducing its bug and watching it fail:

- `test_the_preview_builds_its_variables_the_same_way_issuance_does` — asserted
  over the whole produced vocabulary, not the two keys that were missing, so the
  next name added is covered the day it appears.
- `test_the_preview_previews_the_orgs_own_branding`.
- `test_a_traced_preview_is_drawn_on_the_real_artwork` — compares a preview with
  artwork against the same preview without it, because a PDF containing an image
  is not evidence on its own; the QR code is an image too.

The popup path is not covered by an automated test. It is a browser default that
neither jsdom nor Playwright's default context reproduces, so an assertion would
pass in both states — which this repo's house rule says is worse than none.
