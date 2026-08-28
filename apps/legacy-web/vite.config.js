import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// The API this dev server proxies to. The port was hardcoded to 8000, which
// meant playwright.config.js could move uvicorn with E2E_API_PORT while the SPA
// went on proxying to 8000 — so the E2E suite silently tested the browser
// against whatever happened to be listening there, including a stale server
// from an earlier session.
const apiTarget = `http://localhost:${process.env.E2E_API_PORT || 8000}`

export default defineConfig({
  plugins: [react()],
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
