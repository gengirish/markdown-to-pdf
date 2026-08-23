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
app/page.tsx                      landing page
app/org/[slug]/dashboard/         Credential Studio (bulk issuance, keys, webhooks)
app/passport/[username]/          public recipient passport, server-rendered
app/claim/[credential_id]/        claim a credential into a passport
components/dashboard/             studio cards, each fetching its own data
lib/api.ts                        typed API client and ApiError
lib/use-api.ts                    useCertForge() — the client, with a Clerk token
```

See `CLAUDE.md` for the conventions this app is held to, including the rule
against rendering data the API did not return.
