import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 注意：target 只填后端源地址，不要带 /api/v1 前缀（/api 代理会原样透传完整路径）
  const apiTarget = env.VITE_API_TARGET || 'http://100.70.20.136:5000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true
        },
        '/socket.io': {
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
  }
}) as any
