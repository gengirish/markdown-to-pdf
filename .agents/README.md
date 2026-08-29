# Vendored agent skills

`.agents/skills/` holds Clerk's published skill packages, checked in so an agent
working in this repo has them without a network fetch. `skills-lock.json` at the
repo root pins each one to its upstream `SKILL.md` hash.

## What was removed, and why

Upstream ships a skill per frontend framework. This repo has exactly two
frontends — `apps/web` (Next.js) and `apps/legacy-web` (React + Vite) — so six
framework packages could never apply here and were pruned:

    clerk-astro-patterns          clerk-nuxt-patterns
    clerk-vue-patterns            clerk-tanstack-patterns
    clerk-chrome-extension-patterns   clerk-react-router-patterns

Their `skills-lock.json` entries went with them, so the lockfile still describes
exactly what is on disk. Every `evals/` directory was also dropped: those are
upstream's own test suites for skill authors, not content a consumer reads.

**Kept skills were not edited.** Their `SKILL.md` files are byte-identical to
upstream so the recorded hashes stay valid. The consequence is that the router
in `clerk/SKILL.md` — and passing mentions in `clerk-setup`, `clerk-orgs` and
`clerk-react-patterns` — still name the six pruned skills. An agent that follows
one of those pointers will find nothing there. That is deliberate: a dangling
pointer is easier to diagnose than a vendored file that silently disagrees with
its own lockfile hash.

## Restoring one

Re-add the package under `.agents/skills/<name>/` and put its entry back in
`skills-lock.json` with the upstream `computedHash`. Source for all of them is
the `clerk/skills` GitHub repository; each lockfile entry records the `skillPath`
it came from.
