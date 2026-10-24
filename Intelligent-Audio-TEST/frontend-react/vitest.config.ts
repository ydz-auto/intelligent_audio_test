import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(import.meta.url)

/**
 * @base-ui/react（1.9.0）用 package.json `imports` 的 `#prehydration/*` 子路径，在浏览器与服务端
 * 两套预水合脚本间切换（如 `#prehydration/tabs/indicator`）。vitest 把依赖外部化交给 Node 解析时，
 * 这条包内子路径导入解析失败（`Package import specifier "#prehydration/..." is not defined`），
 * 导致 import 到 `components/ui/tabs` 等组件的套件整体收集失败、0 用例。
 * 测试跑在 jsdom（等价浏览器分支），把 `#prehydration/*` 一律指到包内同一份 stub 预水合脚本
 * （与 package.json `imports` 的 `browser` 分支指向的文件一致）。
 */
function baseUiPrehydrationStub() {
  let stubPath: string | null | undefined
  const resolveStub = () => {
    if (stubPath !== undefined) return stubPath
    try {
      const pkg = require.resolve('@base-ui/react/package.json')
      stubPath = path.join(
        path.dirname(pkg),
        'internals',
        'prehydrationScript.stub.mjs'
      )
    } catch {
      // 包不存在时交回 Vite 默认解析，报错信息仍是原始导入错误
      stubPath = null
    }
    return stubPath
  }

  return {
    name: 'base-ui-prehydration-stub',
    enforce: 'pre' as const,
    resolveId(id: string) {
      if (!id.startsWith('#prehydration/')) return null
      return resolveStub()
    },
  }
}

export default defineConfig({
  plugins: [baseUiPrehydrationStub()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // 组件旁 __tests__/ 目录内 *.test.{ts,tsx}（照 newAPI web 实测：67 目录 229 文件同款粒度）
    include: ['src/**/__tests__/*.{test,spec}.{ts,tsx}'],
    // newAPI vitest.config.ts 实测 20000（含重套件慢 runner）；本卡组件测试取同值保 headroom
    testTimeout: 20000,
    clearMocks: true,
    restoreMocks: true,
    server: {
      deps: {
        // base-ui 走 Vite 内联转换（而非外置给 Node），上面的 #prehydration stub 插件才会生效
        inline: [/@base-ui\/react/],
      },
    },
    // 覆盖率（交付评论需通过数 + 覆盖率口径；@vitest/coverage-v8 随 vitest 同版本安装）
    coverage: {
      provider: 'v8',
      reporter: ['text'],
      include: [
        'src/features/**',
        'src/components/**',
        'src/application/**',
        'src/lib/**',
      ],
      exclude: [
        'src/**/__tests__/**',
        'src/**/*.d.ts',
        'src/routeTree.gen.ts',
        'src/styles/**',
        'src/assets/**',
      ],
    },
  },
})
