import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from '@rsbuild/core'
import { pluginReact } from '@rsbuild/plugin-react'
import { pluginTailwindcss } from '@rsbuild/plugin-tailwindcss'
import { tanstackRouter } from '@tanstack/router-plugin/rspack'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ envMode }) => {
  const isProd = envMode === 'production'
  // 接线侧现状：dev 代理默认指向 5700 真实库栈（INT-1290 起）；INT-1274 引入 env 覆盖，
  // 默认值保留接线侧的 5700，不静默改回 5000。
  const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:5700'

  return {
    plugins: [pluginReact(), pluginTailwindcss({ optimize: false })],
    source: {
      entry: {
        index: './src/main.tsx',
      },
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    html: {
      template: './index.html',
    },
    server: {
      host: '0.0.0.0',
      // 3000 被 newAPI 参照实例（D:\00_code\newAPI\new-api.exe --port 3000）常驻占用（负责人 2026-10-15），
      // React 可视稿 dev server 钉死 5273（避开 5173 Vue 主前端家族与 6xxx UI 测试栈）；strictPort 失败即报错，禁止静默漂移。
      port: 5273,
      strictPort: true,
      // 接线基座（INT-605）：/api 代理到 api_gateway（service_ports.py gateway=5000；
      // 旧 Vue .env.development VITE_API_TARGET=http://localhost:5000 同款）。
      // INT-763：/ws + /socket.io 代理到同一网关——Socket.IO /ws/logs 实时日志通道
      // 引擎挂 /socket.io（app.py:193 mount），命名空间 /ws/logs 走协议内 handshake；
      // ws:true 启用 engine upgrade。
      // INT-1274：dev 代理目标改走 API_PROXY_TARGET 覆盖（docker 化实测栈网关 15000），
      // 默认值保留接线侧的 5700 真实库栈。
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
        '/socket.io': {
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    output: {
      minify: isProd,
      target: 'web',
      distPath: {
        root: 'dist',
      },
    },
    performance: {
      removeConsole: isProd ? ['log'] : false,
    },
    tools: {
      rspack: {
        plugins: [
          tanstackRouter({
            target: 'react',
            autoCodeSplitting: isProd,
          }),
        ],
        module: {
          rules: [
            // 构建期 ?raw 文本资产（content/about.md 中文正文，06_关于.md §7）
            { test: /\.md$/, type: 'asset/source' },
            // INT-1274 字体瘦身：KaTeX 自带 woff2 / woff / ttf 三份同字形字体，
            // katex.min.css 的 @font-face src 按 woff2 → woff → ttf 排列，现代浏览器
            // 只会请求 woff2；另两份（20 个 woff + 20 个 ttf，约 800 kB）不再输出。
            {
              test: /\.(woff|ttf)$/,
              type: 'asset/resource',
              generator: { emit: false },
            },
          ],
        },
      },
    },
  }
})
