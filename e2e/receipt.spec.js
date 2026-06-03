import { test, expect } from '@playwright/test'
import { buildReceiptData, extractReceiptToken, fillReceiptForm } from './helpers/receipt.js'

const apiPort = process.env.E2E_API_PORT || '8000'
const apiOriginPattern = new RegExp(`https?://(127\\.0\\.0\\.1|localhost):${apiPort}`)

/** @param {string} path */
function apiUrl(path) {
  return `http://127.0.0.1:${apiPort}${path}`
}

test.describe('Payment Receipt', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('receipt-tab').click()
    await expect(page.getByRole('heading', { name: 'Receipt Details' })).toBeVisible()
  })

  test('shows receipt form, preview, and live map when address is entered', async ({ page }) => {
    const data = buildReceiptData()

    await fillReceiptForm(page, data)

    await expect(page.getByRole('heading', { name: 'Receipt Preview' })).toBeVisible()
    await expect(page.getByText(data.payer_name).first()).toBeVisible()
    await expect(page.getByText(data.event_name).first()).toBeVisible()
    await expect(page.getByText('INR 2499').first()).toBeVisible()
    await expect(page.getByTestId('receipt-map-preview')).toBeVisible()
    await expect(page.locator('iframe[title="Event location map preview"]')).toBeVisible()
  })

  test('generates receipt via UI and shows shareable link', async ({ page }) => {
    const data = buildReceiptData()

    await fillReceiptForm(page, data)
    await page.getByTestId('receipt-generate-btn').click()

    const result = page.getByTestId('receipt-result')
    await expect(result).toBeVisible({ timeout: 15_000 })
    await expect(result).toContainText('Receipt issued for')
    await expect(result).toContainText(data.payer_name)
    await expect(result.locator('.cert-id-badge')).toContainText(/^RCP-/)

    const shareInput = page.getByTestId('receipt-share-url')
    const shareUrl = await shareInput.inputValue()
    expect(shareUrl).toMatch(apiOriginPattern)
    expect(shareUrl).toMatch(/\/receipt\/.+\..+/)

    await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'View Public Page' })).toBeVisible()
  })

  test('public receipt page shows payment and event details with map embed', async ({ page }) => {
    const data = buildReceiptData()

    await fillReceiptForm(page, data)
    await page.getByTestId('receipt-generate-btn').click()
    await expect(page.getByTestId('receipt-result')).toBeVisible({ timeout: 15_000 })

    const shareUrl = await page.getByTestId('receipt-share-url').inputValue()
    await page.goto(shareUrl)

    await expect(page).toHaveTitle(/Payment Receipt/)
    await expect(page.getByText('Payment Received')).toBeVisible()
    await expect(page.getByText(data.payer_name).first()).toBeVisible()
    await expect(page.getByText(data.event_name).first()).toBeVisible()
    await expect(page.getByText('INR 2499').first()).toBeVisible()
    await expect(page.getByText(data.venue_name).first()).toBeVisible()
    await expect(page.getByText(data.address).first()).toBeVisible()
    await expect(page.locator('iframe.receipt-map-frame, iframe[src*="maps"]')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Download Receipt PDF' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Open in Google Maps' })).toBeVisible()
  })

  test('verify endpoint confirms generated receipt', async ({ page, request }) => {
    const data = buildReceiptData()

    await fillReceiptForm(page, data)
    await page.getByTestId('receipt-generate-btn').click()
    await expect(page.getByTestId('receipt-result')).toBeVisible({ timeout: 15_000 })

    const shareUrl = await page.getByTestId('receipt-share-url').inputValue()
    const token = extractReceiptToken(shareUrl)

    const response = await request.get(`${apiUrl(`/receipt/${token}/verify`)}`)
    expect(response.ok()).toBeTruthy()

    const body = await response.json()
    expect(body.valid).toBe(true)
    expect(body.payer_name).toBe(data.payer_name)
    expect(body.event_name).toBe(data.event_name)
    expect(body.transaction_id).toBe(data.transaction_id)
    expect(body.amount).toBe('INR 2499')
    expect(body.receipt_id).toMatch(/^RCP-/)
  })

  test('downloads receipt PDF from UI', async ({ page }) => {
    const data = buildReceiptData()

    await fillReceiptForm(page, data)
    await page.getByTestId('receipt-generate-btn').click()
    await expect(page.getByTestId('receipt-result')).toBeVisible({ timeout: 15_000 })

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Download PDF' }).click(),
    ])

    expect(download.suggestedFilename()).toMatch(/^Receipt_Playwright_Tester\.pdf$/)
  })

  test('downloads receipt PDF from public page', async ({ page }) => {
    const data = buildReceiptData()

    await fillReceiptForm(page, data)
    await page.getByTestId('receipt-generate-btn').click()
    await expect(page.getByTestId('receipt-result')).toBeVisible({ timeout: 15_000 })

    const shareUrl = await page.getByTestId('receipt-share-url').inputValue()
    await page.goto(shareUrl)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('link', { name: 'Download Receipt PDF' }).click(),
    ])

    expect(download.suggestedFilename()).toMatch(/^Receipt_Playwright_Tester\.pdf$/)
  })
})
