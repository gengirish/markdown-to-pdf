import { test, expect } from '@playwright/test'

test.describe('PDF Cert Generator', () => {
  test('generates certificate via UI and shows shareable link', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('h1')).toBeVisible()

    await page.locator('#participant_name').fill('E2E Test User')
    await page.locator('#course_name').selectOption({ index: 1 })
    await page.locator('#completion_date').fill('2026-04-15')

    await page.getByRole('button', { name: /Generate Certificate/i }).click()
    await expect(page.locator('.cert-result')).toBeVisible({ timeout: 15_000 })

    const shareInput = page.locator('.cert-link-input')
    const shareUrl = await shareInput.inputValue()
    expect(shareUrl).toMatch(/\/certificate\/.+\..+/)
  })
})
