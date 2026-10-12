import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { AUTH_MODE_VALUES } from './src/domain/enums.ts'

// 注意：.env.* 里的 VITE_API_TARGET 必须用 loadEnv 读取（process.env 拿不到 Vite env 文件的值）。
// 兜底默认指向新 FastAPI 网关（shared/config/service_ports.py::API_GATEWAY_PORT=5000）。
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:5000'

  // INT-181：构建期守卫——VITE_AUTH_MODE 必须显式注入（process env），禁止静默默认 off。
  // 仅认显式注入通道（shell 环境变量 / Dockerfile ARG→ENV / CI 注入）；.env* 文件值不作为构建依据。
  if (command === 'build') {
    const injected = process.env.VITE_AUTH_MODE?.trim()
    if (!injected) {
      throw new Error(
        '[INT-181] 构建缺少 VITE_AUTH_MODE：生产构建必须显式注入认证模式，禁止静默默认 off。\n' +
          '注入方式：VITE_AUTH_MODE=<off|dev|prod> npm run build，' +
          '或 docker build --build-arg VITE_AUTH_MODE=<off|dev|prod>（docker/Dockerfile.frontend）。\n' +
          '取值含义见 docs/oauth.md「前端构建期注入（VITE_AUTH_MODE）」。'
      )
    }
    if (!(AUTH_MODE_VALUES as readonly string[]).includes(injected)) {
      throw new Error(
        `[INT-181] VITE_AUTH_MODE="${injected}" 不是合法取值，允许：${AUTH_MODE_VALUES.join(' | ')}。` +
          '取值含义见 docs/oauth.md「前端构建期注入（VITE_AUTH_MODE）」。'
      )
    }
  }

  // https://vitejs.dev/config/
  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 6173,
      host: '0.0.0.0',
      // 放行所有 Host（Tailscale MagicDNS 域名、Cloudflare Tunnel 公网域名等远程访问）
      allowedHosts: true,
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
