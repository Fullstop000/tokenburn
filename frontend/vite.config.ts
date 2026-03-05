import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Build config for dashboard frontend.
 * Output names are stable so backend and tests can reference deterministic paths.
 */
export default defineConfig({
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
})
