import { test, expect } from '@playwright/test'

/**
 * The CertForge public credential surface, end to end through real HTTP.
 *
 * Everything here had unit coverage and no E2E coverage at all — and unit tests
 * cannot see the failures this surface actually produces. A missing `og:image`,
 * a QR that is a data: URI a crawler cannot fetch, a PDF route that 500s on a
 * font: each of those passes a route-table assertion and breaks in a browser.
 *
 * Served by the API rather than the dashboard: `/verify`, `/credentials/*` and
 * `/orgs/*` are rewritten straight through to FastAPI in production, which is
 * why they are reachable here without starting apps/web (which needs Clerk).
 */

const API = `http://127.0.0.1:${process.env.E2E_API_PORT || '8000'}`
const ORG = 'e2e-org'
const API_KEY = 'cf_live_e2e-fixed-key-local-only'

const auth = { Authorization: `Bearer ${API_KEY}` }

async function issue(request, overrides = {}) {
  const res = await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
    headers: auth,
    data: {
      recipient_name: 'Ada Lovelace',
      title: 'Analytical Engines',
      ...overrides,
    },
  })
  expect(res.status(), await res.text()).toBe(201)
  return (await res.json()).data
}

/** Read one <meta> value out of the served HTML. */
function meta(html, attr, value) {
  const re = new RegExp(
    `<meta[^>]+${attr}=["']${value}["'][^>]+content=["']([^"']*)["']`,
    'i',
  )
  const alt = new RegExp(
    `<meta[^>]+content=["']([^"']*)["'][^>]+${attr}=["']${value}["']`,
    'i',
  )
  const m = html.match(re) || html.match(alt)
  return m ? m[1] : null
}

test.describe('CertForge public credential', () => {
  test('the viewer carries link-preview metadata a crawler can use', async ({
    request,
    page,
  }) => {
    const cred = await issue(request)

    const res = await page.goto(`${API}/verify/${cred.id}`)
    expect(res.status()).toBe(200)
    const html = await page.content()

    // Populated, not merely present — an empty content="" satisfies a
    // substring check and is exactly the bug worth catching.
    for (const prop of ['og:title', 'og:description', 'og:type', 'og:url', 'og:image']) {
      const value = meta(html, 'property', prop)
      expect(value, `${prop} missing`).toBeTruthy()
      expect(value.length, `${prop} empty`).toBeGreaterThan(0)
    }
    expect(meta(html, 'name', 'twitter:card')).toBeTruthy()
    expect(meta(html, 'name', 'description')).toBeTruthy()

    // og:image must be fetchable. A data: URI renders in a browser and is
    // invisible to LinkedIn, which is why the PNG route exists.
    const ogImage = meta(html, 'property', 'og:image')
    expect(ogImage.startsWith('data:')).toBe(false)
    expect(ogImage).toMatch(/^https?:\/\//)
  })

  test('the page names the credential and its issuer', async ({ request, page }) => {
    const cred = await issue(request, { recipient_name: 'Grace Hopper' })

    await page.goto(`${API}/verify/${cred.id}`)
    await expect(page.locator('.name')).toContainText('Grace Hopper')
    await expect(page.locator('.card')).toContainText('Analytical Engines')
    // The organization, not the global env brand — this product is
    // multi-tenant and the fallback would be wrong here.
    await expect(page.locator('.card-header')).toContainText('E2E Test College')
    await expect(page.locator('.verified')).toBeVisible()
  })

  test('the share and download actions point at real targets', async ({
    request,
    page,
  }) => {
    const cred = await issue(request)
    await page.goto(`${API}/verify/${cred.id}`)

    const linkedin = page.locator('a.btn-linkedin')
    await expect(linkedin).toBeVisible()
    // The share URL must carry this credential, not the bare site.
    expect(await linkedin.getAttribute('href')).toContain(encodeURIComponent(cred.id))

    const download = page.locator('a.btn-download')
    await expect(download).toBeVisible()
    expect(await download.getAttribute('href')).toContain(cred.id)
  })

  test('the JSON-LD block parses and describes this credential', async ({
    request,
    page,
  }) => {
    const cred = await issue(request, { recipient_name: 'Katherine Johnson' })
    await page.goto(`${API}/verify/${cred.id}`)

    const raw = await page
      .locator('script[type="application/ld+json"]')
      .first()
      .textContent()

    // Parsing is the assertion. A block that is present but malformed is worse
    // than none: a consumer sees structured data and gets nothing from it.
    const doc = JSON.parse(raw)
    expect(doc['@type']).toBe('EducationalOccupationalCredential')
    expect(doc.identifier).toBe(cred.id)
    expect(doc.awardedTo?.name).toBe('Katherine Johnson')
  })

  test('the QR is served as real PNG bytes', async ({ request }) => {
    const cred = await issue(request)
    const res = await request.get(`${API}/credentials/${cred.id}/qr.png`)

    expect(res.status()).toBe(200)
    expect(res.headers()['content-type']).toContain('image/png')

    const body = await res.body()
    // PNG magic number. A 200 carrying an HTML error page would pass a status
    // check and break every link preview.
    expect(body.subarray(0, 4).toString('hex')).toBe('89504e47')
  })

  test('the badge document is a dereferenceable Open Badge', async ({ request }) => {
    const cred = await issue(request)
    const res = await request.get(`${API}/credentials/${cred.id}/badge.json`)
    expect(res.status()).toBe(200)

    const badge = await res.json()
    expect(badge.type).toContain('OpenBadgeCredential')
    expect(badge.issuer?.id).toBeTruthy()

    // issuer.id is a URL a validator is expected to fetch. It 404'd in
    // production for a week because nothing served it.
    const issuerPath = new URL(badge.issuer.id).pathname
    const profile = await request.get(`${API}${issuerPath}`, {
      headers: { Accept: 'application/json' },
    })
    expect(profile.status(), `issuer.id ${badge.issuer.id} is not fetchable`).toBe(200)
    expect((await profile.json()).type).toBe('Profile')
  })

  test('the certificate PDF renders on demand', async ({ request }) => {
    const cred = await issue(request)
    const res = await request.get(`${API}/credentials/${cred.id}/pdf`)

    expect(res.status(), await res.text().catch(() => '')).toBe(200)
    expect(res.headers()['content-type']).toContain('application/pdf')
    expect((await res.body()).subarray(0, 4).toString()).toBe('%PDF')
  })

  test('an unknown credential is refused, not rendered blank', async ({ request }) => {
    for (const path of [
      '/verify/CF-2026-NOTREAL',
      '/credentials/CF-2026-NOTREAL/badge.json',
      '/credentials/CF-2026-NOTREAL/qr.png',
      '/credentials/CF-2026-NOTREAL/pdf',
    ]) {
      const res = await request.get(`${API}${path}`)
      expect(res.status(), `${path} should 404`).toBe(404)
    }
  })
})

test.describe('Issuance guards', () => {
  test('a repeated Idempotency-Key returns the original credential', async ({
    request,
  }) => {
    const key = `e2e-${Date.now()}`
    const body = { recipient_name: 'Dorothy Vaughan', title: 'FORTRAN' }

    const first = await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
      headers: { ...auth, 'Idempotency-Key': key },
      data: body,
    })
    const second = await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
      headers: { ...auth, 'Idempotency-Key': key },
      data: body,
    })

    expect(first.status()).toBe(201)
    expect(second.status()).toBe(201)
    expect((await second.json()).data.id).toBe((await first.json()).data.id)
  })

  test('reusing a key with a different body is refused', async ({ request }) => {
    const key = `e2e-clash-${Date.now()}`

    await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
      headers: { ...auth, 'Idempotency-Key': key },
      data: { recipient_name: 'Mary Jackson', title: 'Aeronautics' },
    })
    const clash = await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
      headers: { ...auth, 'Idempotency-Key': key },
      data: { recipient_name: 'Someone Else', title: 'Aeronautics' },
    })

    expect(clash.status()).toBe(409)
  })

  test('the issuing route reports the caller budget', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
      headers: auth,
      data: { recipient_name: 'Annie Easley', title: 'Rocketry' },
    })
    expect(res.status()).toBe(201)
    // Present only while the limiter is actually declared on the route.
    expect(res.headers()['x-ratelimit-limit']).toBeTruthy()
    expect(res.headers()['x-ratelimit-remaining']).toBeTruthy()
  })

  test('an unauthenticated caller cannot issue', async ({ request }) => {
    const res = await request.post(`${API}/api/v1/orgs/${ORG}/credentials`, {
      data: { recipient_name: 'Nobody', title: 'Nothing' },
    })
    expect([401, 403]).toContain(res.status())
  })
})
