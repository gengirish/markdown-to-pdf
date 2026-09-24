import { test, expect } from '@playwright/test'

/**
 * Plans, end to end through the running API.
 *
 * The unit suite proves the gate and the catalog each read BILLING_TIERS. What
 * it cannot prove is the seam a customer actually crosses: the number the
 * public catalog *advertises* is the number the live server *enforces*. This
 * spec reads the limit off `GET /api/v1/tiers` — never a literal — and then
 * walks a real Community org up to it and one past it over HTTP.
 *
 * Against the API directly, like certforge-credential.spec.js, because apps/web
 * needs Clerk and is not started here.
 */

const API = `http://127.0.0.1:${process.env.E2E_API_PORT || '8000'}`
// Seeded by e2e/seed_e2e.py. Its own org, because the template allowance is a
// stock on the org and filling it would change what other specs can do.
const ORG = 'e2e-quota-org'
const auth = { Authorization: 'Bearer cf_live_e2e-quota-key-local-only' }

const HTML = '<html><body><h1>{{name}}</h1></body></html>'

async function catalog(request) {
  const res = await request.get(`${API}/api/v1/tiers`)
  expect(res.status(), await res.text()).toBe(200)
  return (await res.json()).data
}

async function orgTemplates(request) {
  const res = await request.get(`${API}/api/v1/orgs/${ORG}/templates`, { headers: auth })
  expect(res.status(), await res.text()).toBe(200)
  return (await res.json()).data
}

function createTemplate(request, name) {
  return request.post(`${API}/api/v1/orgs/${ORG}/templates`, {
    headers: auth,
    data: { name, html_source: HTML },
  })
}

/** Retries (2 in CI) and a reused local SQLite file both leave templates
 *  behind, and a leftover would turn the first create into a 402. The gate is
 *  a stock, so emptying it is a legitimate reset rather than a workaround. */
async function emptyOrg(request) {
  for (const t of await orgTemplates(request)) {
    const res = await request.delete(`${API}/api/v1/orgs/${ORG}/templates/${t.id}`, {
      headers: auth,
    })
    expect(res.status(), await res.text()).toBe(200)
  }
}

test.describe('CertForge plans', () => {
  test('the catalog is public, ordered, and never leaks the -1 sentinel', async ({
    request,
  }) => {
    // No Authorization header: the pricing page is for people without an account.
    const tiers = await catalog(request)

    expect(tiers.map((t) => t.key)).toEqual(['community', 'pro'])

    const prices = tiers.map((t) => t.price_paise)
    expect(prices).toEqual([...prices].sort((a, b) => a - b))
    expect(tiers[0].price_paise).toBe(0)

    // Scale is a real tier the gates honour, but it is hand-sold: `listed` is
    // false, so it must not reach the pricing page. A card for it would be a
    // button with no checkout behind it.
    expect(tiers.find((t) => t.key === 'scale')).toBeUndefined()
    for (const t of tiers) {
      expect(t.monthly_quota).not.toBe(-1)
      expect(t.template_limit).not.toBe(-1)
    }
  })

  test('a Community org is held to exactly the allowance the catalog advertises', async ({
    request,
  }) => {
    const community = (await catalog(request)).find((t) => t.key === 'community')
    const limit = community.template_limit
    // Community must be able to reach the feature at all — a 0 here is the
    // flat gate this replaced.
    expect(limit).toBeGreaterThan(0)

    await emptyOrg(request)

    for (let n = 0; n < limit; n++) {
      const res = await createTemplate(request, `Allowed ${n}`)
      expect(res.status(), await res.text()).toBe(201)
    }

    const refused = await createTemplate(request, 'One too many')
    expect(refused.status(), await refused.text()).toBe(402)

    const { success, error } = await refused.json()
    expect(success).toBe(false)
    // Typed apart from a credential-quota 402, which the dashboard words differently.
    expect(error.type).toBe('template_limit_reached')
    expect(error.details.limit).toBe(limit)
    expect(error.details.tier).toBe('community')
    // Only what can actually be bought: Scale holds more templates but is
    // hand-sold, and offering it here is an upgrade prompt that dead-ends.
    expect(error.details.upgrades.map((u) => u.tier)).toEqual(['pro'])
  })

  test('deleting a template gives the slot back', async ({ request }) => {
    const limit = (await catalog(request)).find((t) => t.key === 'community').template_limit

    await emptyOrg(request)
    for (let n = 0; n < limit; n++) {
      expect((await createTemplate(request, `Fill ${n}`)).status()).toBe(201)
    }
    expect((await createTemplate(request, 'Blocked')).status()).toBe(402)

    const [first] = await orgTemplates(request)
    const dropped = await request.delete(`${API}/api/v1/orgs/${ORG}/templates/${first.id}`, {
      headers: auth,
    })
    expect(dropped.status(), await dropped.text()).toBe(200)

    const again = await createTemplate(request, 'Room again')
    expect(again.status(), await again.text()).toBe(201)
  })
})
