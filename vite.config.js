import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/certificate': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/invoice': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
