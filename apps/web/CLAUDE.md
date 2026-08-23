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

## Version-specific gotchas

- `params` in every dynamic route is a `Promise`. Server components `await` it;
  client components read it with React's `use()`.
- Clerk v7 removed `<SignedIn>` / `<SignedOut>`. The replacement `<Show>`
  resolves server-side and needs `clerkMiddleware`, which this app does not
  install, so branch on `useAuth()` / `useUser()` instead. Server-side `auth()`
  and `currentUser()` will not work until a `proxy.ts` running
  `clerkMiddleware()` is added.
- `app/global-error.tsx` is load-bearing: without it, Next prerenders its own
  `/_global-error` through `ClerkProvider` and the build fails when no Clerk
  publishable key is set.
