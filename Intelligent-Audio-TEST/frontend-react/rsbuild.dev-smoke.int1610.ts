import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from '@rsbuild/core'
import { pluginReact } from '@rsbuild/plugin-react'
import { pluginTailwindcss } from '@rsbuild/plugin-tailwindcss'
import { tanstackRouter } from '@tanstack/router-plugin/rspack'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// TEMPORARY smoke-only config (INT-1610 integration). Proxy points at the docker
// gateway :15000 instead of the local :5000 stack. Delete after use.
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
      host: '127.0.0.1',
      port: 5273,
      strictPort: true,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:15000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'http://127.0.0.1:15000',
          changeOrigin: true,
          ws: true,
        },
        '/socket.io': {
          target: 'http://127.0.0.1:15000',
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
  }
})
