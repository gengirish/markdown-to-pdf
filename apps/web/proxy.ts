import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Protect by exception, not by default.
//
// `clerk init` scaffolds the opposite — auth.protect() on everything except
// /sign-in and /sign-up. That is the right default for most apps and the wrong
// one here: CertForge exists to serve PUBLIC verifiable credentials. Under the
// scaffolded rule you would have to sign in to view a passport, or even to see
// the credential you are being invited to claim, which defeats the product.
//
// Default-allow is safe here because the pages are thin clients: every
// /api/v1 route authorises server-side against the database (require_org_role,
// OrgMember), so a page being reachable leaks nothing on its own. The failure
// mode of the opposite choice — a new public page silently becoming gated and
// quietly breaking verification — is both likelier and worse.
//
// Anything that renders org-owned data or acts on a session goes in here.
//
// The singular/plural split is load-bearing, not a typo:
//
//   /org/{slug}/...  the private dashboard  — protected, listed below
//   /orgs/{slug}     the public issuer page — anonymous, rewritten to the API
//
// This was "/org(.*)", which matches "/orgs/acme" too: `(.*)` accepts the "s".
// That would have put an Open Badges issuer.id behind auth.protect(), so a
// badge consumer dereferencing it would be redirected to a sign-in page rather
// than served a Profile. Anchoring the slash keeps the two namespaces apart.
const isProtectedRoute = createRouteMatcher([
  "/org",
  "/org/(.*)",
]);

export default clerkMiddleware(async (auth, request) => {
  if (isProtectedRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    // Clerk's auto-proxy path — must be matched or handshake/satellite flows break.
    "/__clerk/:path*",
  ],
};
