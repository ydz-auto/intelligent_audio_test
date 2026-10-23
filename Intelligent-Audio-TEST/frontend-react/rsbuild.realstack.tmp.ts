/**
 * 临时接线实测配置（INT-1433 验收用，用毕即删不提交）：
 * 覆盖 rsbuild.config.ts 的代理 target → 真实库栈 5700，端口 → 5333。
 * 启动：pnpm dev --config rsbuild.realstack.tmp.ts
 */
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
    source: { entry: { index: './src/main.tsx' } },
    resolve: { alias: { '@': path.resolve(__dirname, './src') } },
    html: { template: './index.html' },
    server: {
      host: '0.0.0.0',
      port: 5333,
      strictPort: true,
      proxy: {
        '/api': { target: 'http://127.0.0.1:5700', changeOrigin: true },
        '/ws': { target: 'http://127.0.0.1:5700', changeOrigin: true, ws: true },
        '/socket.io': { target: 'http://127.0.0.1:5700', changeOrigin: true, ws: true },
      },
    },
    output: { minify: isProd, distPath: { root: 'dist' } },
    performance: { removeConsole: isProd ? ['log'] : false },
    tools: {
      rspack: {
        plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: isProd })],
        module: { rules: [{ test: /\.md$/, type: 'asset/source' }] },
      },
    },
  }
})
