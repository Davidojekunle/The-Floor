import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Runs next to the old frontend (5173). API calls go through the dev proxy,
// so the backend's CORS settings don't need to change.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // 127.0.0.1, not localhost: on Windows localhost can try IPv6 first and stall about a second per request.
      // ws: true also forwards the live socket (/api/v1/ws).
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
