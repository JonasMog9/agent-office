import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Phaser alone is ~1.2 MB minified; it loads once and is cached.
  build: { chunkSizeWarningLimit: 2000 },
})
