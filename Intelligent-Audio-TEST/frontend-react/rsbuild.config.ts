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
      // 临时：真实库走查（INT-1205）指向真实库栈 5700（主库 intelligent_audio_test），
      // dev 端口用 5300~5399 段空闲端口。走查结束会还原为 5273 + 5000。
      port: 5273,
      strictPort: true,
      proxy: {
        '/api': {
          target: 'http://localhost:15000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'http://localhost:15000',
          changeOrigin: true,
          ws: true,
        },
        '/socket.io': {
          target: 'http://localhost:15000',
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
          ],
        },
      },
    },
  }
})
