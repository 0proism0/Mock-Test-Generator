import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// React front-end for MockTest Maker.
// Dev: `npm run dev` proxies the JSON API to the stdlib Python server (app/server.py).
// Prod: `npm run build` emits ./dist, which app/server.py serves at "/" when present
//       (legacy app/static/index.html stays as the fallback).

// Port of the Python API. Keep in sync with app/server.py (env MOCKTEST_PORT, default 8020).
const apiPort = process.env.MOCKTEST_PORT ?? '8020'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
