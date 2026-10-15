import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// React front-end for MockTest Maker.
// Dev: `npm run dev` proxies the JSON API to the stdlib Python server (app/server.py).
// Prod: `npm run build` emits ./dist, which app/server.py serves at "/" when present
//       (legacy app/static/index.html stays as the fallback).
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
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
