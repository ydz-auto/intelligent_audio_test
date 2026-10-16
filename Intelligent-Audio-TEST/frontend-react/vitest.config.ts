import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
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
