import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Les appels a /api sont rediriges vers le backend Flask
    proxy: { '/api': 'http://127.0.0.1:5000' },
  },
})
