import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:5000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host:'0.0.0.0',
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true
      },
      '/socket.io': {
        target: apiTarget,
        changeOrigin: true,
        ws: true  // WebSocket
      },
      '/ws': {
        target: apiTarget,
        changeOrigin: true,
        ws: true
      }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/__tests__/**/*.spec.ts'],
  },
}) as any
