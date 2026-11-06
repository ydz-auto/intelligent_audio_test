import { createFileRoute, redirect } from '@tanstack/react-router'

import { requireAnyPermission } from '@/application/auth/route-guards'

/**
 * 端到端测试 /E2ETest（INT-486 合并：redirect → /start-test）。
 * 旧链兼容（收藏夹/外部链接不断链）：同守卫后跳开始测试合并入口。
 * 2026-10-16 追加口径：开始测试不再分 E2E/API 模式，直接跳单流程入口。
 * beforeLoad：task:execute 或 algorithm:read（INT-449 只读观察）→ /start-test；其余 /403?from。
 */
export const Route = createFileRoute('/_authenticated/E2ETest')({
  beforeLoad: ({ location }) => {
    requireAnyPermission(['task:execute', 'algorithm:read'], location)
    throw redirect({ to: '/start-test' })
  },
})
