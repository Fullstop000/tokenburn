import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Build config for dashboard frontend.
 *
 * Production build: `npm run build`
 *   - Outputs stable asset names so the Python backend can serve them deterministically.
 *
 * Dev server: `npm run dev`
 *   - Runs Vite HMR on :5173.
 *   - All /api/* requests are proxied to the Python backend on :8787.
 *   - VITE_API_PORT env var lets you override the backend port.
 */
export default defineConfig(({ command }) => ({
  plugins: [react()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/dashboard.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: command === 'serve' ? {
    port: Number(process.env.VITE_PORT ?? 5173),
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.VITE_API_PORT ?? 8787}`,
        changeOrigin: false,
      },
    },
  } : undefined,
}))
