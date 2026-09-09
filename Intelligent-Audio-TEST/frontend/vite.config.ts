import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// 注意：.env.* 里的 VITE_API_TARGET 必须用 loadEnv 读取（process.env 拿不到 Vite env 文件的值）。
// 兜底默认指向新 FastAPI 网关（shared/config/service_ports.py::API_GATEWAY_PORT=5000）。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:5000'

  // https://vitejs.dev/config/
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 6173,
      host: '0.0.0.0',
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
  }
}) as any
