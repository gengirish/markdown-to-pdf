import { defineConfig, devices } from '@playwright/test'

const apiPort = process.env.E2E_API_PORT || '8000'
const webPort = process.env.E2E_WEB_PORT || '5173'
const apiOrigin = `http://127.0.0.1:${apiPort}`
const webOrigin = `http://127.0.0.1:${webPort}`
const prodBaseURL = process.env.E2E_BASE_URL?.replace(/\/$/, '')
const isProdE2E = Boolean(prodBaseURL)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['html', { open: 'never' }]],
  timeout: 60_000,
  use: {
    baseURL: prodBaseURL || webOrigin,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: isProdE2E
    ? undefined
    : [
        {
          command: `python -m uvicorn api.index:app --host 127.0.0.1 --port ${apiPort}`,
          url: `${apiOrigin}/api/health`,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            CERT_SECRET_KEY: process.env.CERT_SECRET_KEY || 'e2e-test-secret-local-only',
          },
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
          url: webOrigin,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
      ],
})
