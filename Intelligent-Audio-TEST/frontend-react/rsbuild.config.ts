import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from '@rsbuild/core'
import { pluginReact } from '@rsbuild/plugin-react'
import { pluginTailwindcss } from '@rsbuild/plugin-tailwindcss'
import { tanstackRouter } from '@tanstack/router-plugin/rspack'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ envMode }) => {
  const isProd = envMode === 'production'

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
      proxy: {
        '/api': {
          target: 'http://localhost:5000',
          changeOrigin: true,
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
          ],
        },
      },
    },
  }
})
