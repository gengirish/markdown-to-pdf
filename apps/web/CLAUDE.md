@AGENTS.md

# apps/web — CertForge dashboard

Next.js 16 + Clerk, deployed to `certforge.intelliforge.tech`. It is a pure
client of the FastAPI service on `api.certforge.intelliforge.tech`; it has no
route handlers and no database of its own.

## Never fake data

This app previously shipped a hardcoded passport, a claim button that resolved a
`setTimeout` and reported success, and a CSV upload that announced 150 issued
credentials without a network call. That is worse than no feature at all —
someone reading the screen believes it.

Where the API has no endpoint, render an empty or unavailable state that says so.
Two live examples: the plan card names the tier but states that usage reporting
and self-serve upgrades do not exist (`POST /orgs/{slug}/checkout` returns a
placeholder URL server-side), and `ApiStatusBadge` probes `/api/health` rather
than hardcoding "operational".

## Talking to the API

Everything goes through `lib/api.ts`. Do not call `fetch` against the API from a
component.

- `useCertForge()` (`lib/use-api.ts`) returns a client that attaches the Clerk
  session JWT. Use it for anything under `/api/v1` that requires a member.
- `publicApi` is the anonymous client, for `/api/health`, `GET /orgs/{slug}`,
  passports, and verification.
- Every method rejects with `ApiError`; `toApiError(err)` normalises an unknown
  catch value. The API answers failures in three different shapes (a 200 with
  `{"success": false, …}`, a real status with a bare `{"error": …}`, and
  FastAPI's `{"detail": …}`) — `lib/api.ts` is the only place that knows this.
- Base URL comes from `NEXT_PUBLIC_CERTFORGE_API_URL`; see `.env.example`.

New endpoint? Add a typed method and its response interface to `CertForgeClient`
rather than reaching around it.

## The design system

`app/globals.css` is the single source of the product's look: a warm light palette
(`#FBFAF9` ground, `#17171A` ink, `#0E6B58` accent), Space Grotesk for display type,
JetBrains Mono for anything read character by character. Every colour is a
`--cf-*` custom property, re-exported to Tailwind through `@theme inline` as
`--color-ground`, `--color-ink`, `--color-accent`, and so on.

**Use a token, never a literal.** `bg-ground` rather than `bg-[#0a0a0a]`,
`text-ground` on an accent background rather than `text-white`. The literals are not
a style preference — they do not invert with the theme, so each one is a contrast bug
waiting in the mode it was not written in. Three `bg-[#0a0a0a]` literals and one
`text-white` survived the redesign's own sweep precisely because that sweep matched
Tailwind class names and could not see them.

Contrast is measured, not eyeballed. White on the dark-mode accent measured 2.42:1;
`text-ground` passes in both (6.17 light, 7.66 dark). The design's own `faint`
(`#8A857A`) measured 3.67:1 on white — below what small label text needs — and was
walked down its own hue to `#777369`, the one deliberate deviation from the source
design's light values.

Dark-mode values are **not** from the design, which specifies light only. They are
derived from the same warm-neutral logic and flagged as such in `globals.css`. If a
dark ramp ever arrives, replace that block wholesale rather than reconciling it.

## Theme: two selectors that must stay duplicated

`lib/theme.ts` owns the light/dark override; `components/theme-toggle.tsx` is the
switch, wired into `SiteHeader` (every public page) and the dashboard's own header.

The source of truth is the `data-theme` attribute on `<html>`, not React state — it
has to be, because the inline bootstrap script in `layout.tsx` sets it synchronously
before React mounts, so no frame paints the wrong theme.

- The dark palette is defined **twice**, under `:root[data-theme="dark"]` and under
  `@media (prefers-color-scheme: dark) { :root:not([data-theme]) }`. Do not collapse
  them. A visitor with JavaScript disabled never gets the attribute at all, and the
  media rule is their only path to a dark theme; the `:not([data-theme])` scope is
  what lets an explicit `light` win over a dark OS setting.
- `watchSystemTheme` follows the OS live for exactly as long as nobody has clicked
  the toggle, and stops the moment somebody has.
- **Do not read the DOM in a lazy `useState` initializer to skip a placeholder
  frame.** It reads correctly on the client's hydration pass and not on the server's,
  so the two passes render *different element types* in one slot — React discards and
  rebuilds the subtree, which is worse than the flash it was avoiding. Keep the
  element type constant across both passes and correct the value after mount.

## The issue wizard, and what it is allowed to flag

`components/dashboard/issue-wizard.tsx` is Upload → Review → Sign → Report over
`POST /orgs/{slug}/credentials/bulk` — which is one call, with no server-side dry
run, no per-row skip, and no duplicate check against the org's existing credentials.
Every problem Steps 1 and 2 report is therefore checked **in the browser, against the
file alone**.

- Parsing goes through `lib/csv.ts`, a hand-verified RFC4180 reader (quoted commas,
  doubled quotes, embedded newlines, CRLF, no trailing newline). Not a `split(",")`:
  the server parses with Python's `csv.DictReader`, so a name like `"Rao, Ananya"`
  would misalign every column after it — silently.
- Header case is preserved exactly, because `DictReader` keys on the literal text.
- Excluding or editing a row **rebuilds the CSV client-side** before it is sent,
  since the server has no per-row skip.
- **A fabricated problem is worse than a missed one.** Two checks the source design
  asked for are deliberately absent — "domain has no MX record" (no DNS capability
  exists here) and "already issued" (no email-search endpoint exists). What is
  checked is what the file can prove: the server's own missing-name/missing-title
  rule, a malformed address, and a duplicate email within the same file.
- Once the POST lands the batch exists and cannot be un-created, so the step
  indicator only allows jumping back to a step already reached. A Sign-step failure
  returns to Review with edits and exclusions **intact** — "start over" belongs on
  the Report step, not on an error.

## Version-specific gotchas

- `params` in every dynamic route is a `Promise`. Server components `await` it;
  client components read it with React's `use()`.
- Clerk v7 removed `<SignedIn>` / `<SignedOut>`; the replacement is `<Show>`.
  This entry used to say `clerkMiddleware` was not installed — it is now.
  `proxy.ts` (Next 16's name for middleware) runs it, so server-side `auth()`,
  `currentUser()` and `<Show>` all work.
- **`proxy.ts` protects by exception, not by default**, and the namespaces are
  not interchangeable:

  ```
  /org/{slug}/...   the signed-in dashboard    protected
  /orgs/{slug}      the public issuer profile  anonymous, rewritten to the API
  ```

  The matcher is anchored as `/org/(.*)`. It was `/org(.*)`, which also matches
  `/orgs/acme` because `(.*)` accepts the `s` — that put an Open Badges
  `issuer.id` behind auth, so a badge consumer dereferencing it met a sign-in
  redirect instead of a Profile.

- **A `vercel.json` rewrite does not bypass `proxy.ts`.** Middleware runs first,
  on rewritten paths too. `/verify`, `/credentials` and `/orgs` are therefore
  excluded from the matcher: they are pure passthrough to the API, they render
  nothing in this app, and they are the URLs inside printed QR codes. Running
  Clerk on them means a Clerk misconfiguration takes credential verification
  down — which is not hypothetical, it is how a preview deployment answered 500
  on `/verify`. A test fails if those exclusions are removed.

- **Preview deployments currently 500 on every page.** All three env vars are
  set on Production only, so `clerkMiddleware` throws `Missing publishableKey`.
  Fixing it needs Clerk *development-instance* keys; copying production secrets
  onto preview URLs is real exposure.

- `app/global-error.tsx` is load-bearing: without it, Next prerenders its own
  `/_global-error` through `ClerkProvider` and the build fails when no Clerk
  publishable key is set.
