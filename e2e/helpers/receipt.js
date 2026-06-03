/**
 * @param {import('@playwright/test').Page} page
 * @param {Record<string, string>} data
 */
export async function fillReceiptForm(page, data) {
  await page.getByLabel('Payer Name').fill(data.payer_name)
  await page.getByLabel('Amount').fill(data.amount)

  if (data.currency) {
    await page.getByLabel('Currency').selectOption(data.currency)
  }

  if (data.payment_date) {
    await page.getByLabel('Payment Date').fill(data.payment_date)
  }

  if (data.payment_method) {
    await page.getByLabel(/Payment Method/).fill(data.payment_method)
  }

  await page.getByLabel('Transaction ID').fill(data.transaction_id)
  await page.getByLabel('Event Name').fill(data.event_name)
  await page.getByLabel('Event Date').fill(data.event_date)

  if (data.event_time) {
    await page.getByLabel(/Event Time/).fill(data.event_time)
  }

  if (data.venue_name) {
    await page.getByLabel(/Venue Name/).fill(data.venue_name)
  }

  if (data.address) {
    await page.getByLabel(/^Address/).fill(data.address)
  }

  if (data.maps_url) {
    await page.getByLabel(/Google Maps URL/).fill(data.maps_url)
  }

  if (data.description) {
    await page.getByLabel(/^Description/).fill(data.description)
  }
}

/** @returns {Record<string, string>} */
export function buildReceiptData(overrides = {}) {
  return {
    payer_name: 'Playwright Tester',
    event_name: 'E2E AI Workshop',
    event_date: '2026-07-15',
    event_time: '10:00 AM IST',
    venue_name: 'IntelliForge Learning Hub',
    address: 'MG Road, Bengaluru, Karnataka 560001',
    amount: '2499',
    currency: 'INR',
    payment_date: '2026-06-03',
    payment_method: 'UPI',
    transaction_id: `e2e-${Date.now()}`,
    description: 'Automated Playwright registration',
    ...overrides,
  }
}

/** @param {string} shareUrl */
export function extractReceiptToken(shareUrl) {
  const match = shareUrl.match(/\/receipt\/([^/?#]+)/)
  if (!match) {
    throw new Error(`Could not extract receipt token from URL: ${shareUrl}`)
  }
  return match[1]
}
