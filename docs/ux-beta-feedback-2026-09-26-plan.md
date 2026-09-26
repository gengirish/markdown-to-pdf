# Beta feedback, 26 September 2026 — plan

Nine points from a first-time user walking through sign-up, "Make CertForge
yours", branding and templates. Each is mapped to what causes it in the code,
then to the change. All of it is `apps/web/` plus one Clerk instance setting;
nothing touches the API contract, the DB schema or the legacy freeze.

| # | Feedback | Cause | Change |
|---|---|---|---|
| 1 | Sign-up demands a 15-character password | Clerk instance setting `auth_password.min_length: 15` (not in this repo) | `clerk config patch` to 8. Breach checking (HIBP, also on sign-in) stays on, which is the control that actually refuses weak passwords. |
| 2 | "Make CertForge yours" steps jump to a tab and you scroll down to find the form | Each step's button calls `onSelectTab`, which switches the tab *below* a 450px card | A step's button expands that step in place — the real form opens directly under it. One step open at a time; "Open full tab" stays available. |
| 3 | No live preview while editing | The only preview is "Preview PDF", a server render in a new tab | A live sketch of the guided certificate beside the branding form and the guided template editor, redrawn on every keystroke. Labelled a sketch; the PDF render stays the final word. |
| 4 | "Footer line" — where does it go? | The field has a placeholder and nothing else | The sketch marks where each field prints; focusing a field highlights its place on the certificate. |
| 5 | Pick colours, upload a logo → colours reset (bug) | `BrandingCard` re-prefills every field from `org` whenever `org` changes; the logo upload refetches `org`, wiping unsaved colours | Prefill once per org; a later `org` update never overwrites a field the person has edited. Show "Unsaved changes" so the two save models (logo instant, colours on Save) are visible. |
| 6 | Changing "Base layout" should change the heading | `layout` is an independent select; heading/opening/closing stay on the old layout's text | Picking a layout swaps in that layout's heading and wording — but only for fields still holding a stock default, so custom text is never overwritten. Pure function, unit-tested. |
| 7 | Show one example certificate with the parts named | — | Same sketch as 3/4, with numbered callouts (Heading, Opening line, Recipient, Title, Signature, QR, Footer). |
| 8 | "Credentials" is not explained | The word is used everywhere and defined nowhere | One plain definition — *one certificate for one person: a PDF, a permanent verify link/QR and a digital badge* — on the setup step, the Issue tab and the Credentials tab. |
| 9 | Pro price feels high | Pricing decision, not a defect | **No code change.** Talking points for the call below. |

## Order of work

1. #5 (bug) — smallest, most certain.
2. #6 — `lib/template-presets.ts` + test.
3. #3/#4/#7 — `components/dashboard/certificate-sketch.tsx`, used by branding and the guided editor.
4. #2 — checklist accordion rendering the real cards inline.
5. #8 — copy.
6. #1 — Clerk config (a live instance setting; the dev instance currently serves production).

Verify: `npm run lint`, `npm run typecheck`, `npm test` in `apps/web`, then drive the
dashboard in a browser.

## What the sketch is and is not

It is an HTML/CSS replica of `TEMPLATE_SHELL` in `apps/api/api/services/templates.py`,
so it is a **third copy of the guided layout** (the API's HTML and the PDF being the
first two). That is the drift risk this codebase keeps warning about, so:

- it is labelled a sketch, and "Preview PDF" stays next to it as the real render;
- it only draws the guided layout — traced and hand-written HTML templates keep the
  canvas and the PDF preview they have now;
- the fallback colours (`#1e293b`, `#d4af37`) and footer text mirror
  `build_render_variables` in `api/services/rendering.py`; a change there needs one here.

## #9 — pricing, for the call

Current (`BILLING_TIERS`): Community free, 50/month, 1 CSV batch; Pro ₹1,999/month,
1,000/month, artwork + API keys. Reference point is CertPie: ₹999 for 500,
₹2,499 unlimited (checked 22 Sep).

- Per certificate, Pro is ₹2.00 — the same as CertPie's ₹999/500. The sticker is
  higher because the bundle is twice the size.
- A cohort founder issuing 60–200 a month pays for 1,000 they do not use. The gap is
  between free (50) and ₹1,999.
- Options: (a) a ₹799–999 tier at ~300/month; (b) annual billing at ~2 months free;
  (c) one-off cohort packs (e.g. ₹499 per 200) for occasional issuers; (d) keep the
  price and lead with what CertPie does not have (verify links, Open Badges, passport).
- Any change is `BILLING_TIERS` + a Dodo product — the pricing page reads the catalog,
  so no page copy to edit.
