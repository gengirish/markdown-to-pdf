# CertForge dashboard

The Next.js app behind `certforge.intelliforge.tech`: a landing page, the
Credential Studio for an organization, recipient passports, and the credential
claim flow.

It holds no data. Every read and write goes to the CertForge API at
`api.certforge.intelliforge.tech` (see `apps/api/`) through the typed client in
`lib/api.ts`. Sign-in is Clerk; the session JWT is forwarded as a bearer token.

## Running it

```bash
cp .env.example .env.local     # then fill in the Clerk keys
npm install                    # from the repo root — this is a workspace
npm run dev  --workspace=web   # http://localhost:3000
npm run build --workspace=web
npm run lint  --workspace=web
```

Set `NEXT_PUBLIC_CERTFORGE_API_URL=http://localhost:8000` in `.env.local` to
develop against a locally running API.

## Layout

```
app/page.tsx                      landing page, verify lookup, live status board
app/globals.css                   the design tokens every colour comes from
app/layout.tsx                    fonts, providers, and the pre-hydration theme script
app/org/[slug]/dashboard/         Credential Studio
app/passport/[username]/          public recipient passport, server-rendered
app/claim/[credential_id]/        claim a credential into a passport
components/site-header.tsx        header for the public pages
components/theme-toggle.tsx       light/dark switch
components/verify-lookup.tsx      credential-ID lookup on the landing page
components/specimen-certificate.tsx  the sample certificate the landing page shows
components/dashboard/             studio cards, each fetching its own data
components/dashboard/issue-wizard.tsx  Upload → Review → Sign → Report bulk issuance
components/dashboard/ui.tsx       Card, Eyebrow, StatusTag, buttonClass, inputClass
lib/api.ts                        typed API client and ApiError
lib/use-api.ts                    useCertForge() — the client, with a Clerk token
lib/csv.ts                        RFC4180 parse/serialise, for the wizard
lib/theme.ts                      data-theme on <html>, plus the bootstrap script
```

## Look and feel

One theme, defined once. `app/globals.css` holds every colour as a `--cf-*` custom
property and re-exports it to Tailwind via `@theme inline`, so components write
`bg-ground` and `text-accent` rather than hex literals. Light and dark both ship; the
toggle writes `data-theme` on `<html>` and persists the choice, and until somebody
picks, the OS setting is followed live.

See `CLAUDE.md` for the conventions this app is held to — the rule against rendering
data the API did not return, why the dark palette is deliberately declared twice, and
what the issue wizard is and is not allowed to flag.
