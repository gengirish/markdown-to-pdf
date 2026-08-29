import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const configDir = dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
// The API this dev server proxies to. The port was hardcoded to 8000, which
// meant playwright.config.js could move uvicorn with E2E_API_PORT while the SPA
// went on proxying to 8000 — so the E2E suite silently tested the browser
// against whatever happened to be listening there, including a stale server
// from an earlier session.
const apiTarget = `http://localhost:${process.env.E2E_API_PORT || 8000}`

export default defineConfig({
  plugins: [react()],
  // The static assets live in the repo root's public/, not in this app — the
  // certificate branding PNGs are shared with scripts/build_sports_handout.py,
  // which reads them off disk from there. Vite's default publicDir would be
  // apps/legacy-web/public, which does not exist, so nothing was copied into
  // dist/ at all: /favicon.svg fell through to the SPA catch-all in
  // vercel.json and answered 200 with the app shell, and /branding/* 404'd.
  // That favicon is also the `logo_url` advertised by /.well-known/ai-plugin.json.
  publicDir: resolve(configDir, '../../public'),
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/certificate': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/invoice': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
