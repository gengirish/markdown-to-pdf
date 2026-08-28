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
          // The seed is chained ahead of uvicorn rather than run as a global
          // setup step, because globalSetup and webServer race — the server can
          // be answering before the org and API key exist.
          command:
            `python ../../e2e/seed_e2e.py && ` +
            `python -m uvicorn api.index:app --host 127.0.0.1 --port ${apiPort}`,
          cwd: 'apps/api',
          url: `${apiOrigin}/api/health`,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            CERT_SECRET_KEY: process.env.CERT_SECRET_KEY || 'e2e-test-secret-local-only',
            // A disposable SQLite file, so the CertForge surface is reachable
            // without provisioning Postgres. Both surfaces cope: the legacy
            // psycopg2 layer fails to connect and degrades to its hardcoded
            // course list, which is the documented behaviour when the database
            // is absent.
            DATABASE_URL: process.env.E2E_DATABASE_URL || 'sqlite:///e2e.sqlite',
            // The embedded Procrastinate worker needs real Postgres. Bulk
            // issuance is therefore out of scope for E2E; single issuance,
            // which runs inline, is what these specs exercise.
            PROCRASTINATE_APPLY_SCHEMA: '0',
          },
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
          cwd: 'apps/legacy-web',
          url: webOrigin,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            // vite.config.js reads this to aim its proxy. Without it the SPA
            // talks to whatever is on 8000 while uvicorn runs elsewhere.
            E2E_API_PORT: apiPort,
          },
        },
      ],
})
