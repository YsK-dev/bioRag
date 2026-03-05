import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // Important for docker
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://app:8000', // Points to the FastAPI service in docker-compose
        changeOrigin: true,
        secure: false,
        timeout: 300000,
      }
    }
  }
})
