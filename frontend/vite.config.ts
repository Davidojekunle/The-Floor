import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // API calls go to the backend through this proxy, so the refresh cookie is same-origin.
    // 127.0.0.1, not localhost: on Windows localhost can try IPv6 first and stall.
    proxy: { '/api': { target: 'http://127.0.0.1:8000', ws: true } },
  },
})