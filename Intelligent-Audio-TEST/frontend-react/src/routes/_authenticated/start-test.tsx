import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { z } from 'zod'

import { requireAnyPermission } from '@/application/auth/route-guards'
import { TestExecutionPage } from '@/features/test-execution'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

/**
 * 开始测试 /start-test（INT-486 合并入口：端到端+API 合并单入口，单流程——2026-10-16
 * 追加口径不再分 E2E/API 模式，步骤二同屏选设备+API）。
 * 10_测试执行.md §3.1.1/§3.2；不再有「选择算法」步骤（算法切换已全局化 INT-436/442）。
 * beforeLoad 守卫分支：持有 task:execute 走完整交互态；algo_engineer（无 task:execute、
 * 按 INT-449 只读权限点以 algorithm:read 标识）走只读观察态，URL 直达不再 /403；
 * 其余无权限角色（device_admin/guest）仍整页 /403。
 * validateSearch：step（0-3 白名单 catch 0）+ view（表格/卡片，zod .catch('table')）。
 */
export const startTestSearchSchema = z
  .object({
    step: z.coerce.number().int().min(0).max(3).catch(0),
    view: z.enum(['table', 'card']).catch('table'),
  })
  .partial()
  .catch({})

function StartTestPageRoute() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as unknown as {
    step?: number
    view?: 'table' | 'card'
  }
  return (
    <TestExecutionPage
      initialView={search.view ?? 'table'}
      onViewChange={(view) => navigateWithSearch(navigate, { view })}
    />
  )
}

export const Route = createFileRoute('/_authenticated/start-test')({
  validateSearch: startTestSearchSchema,
  beforeLoad: ({ location }) => {
    // task:execute 完整交互态 / algorithm:read（INT-449 algo 只读观察）任一放行；
    // 其余无权限角色（device_admin/guest）整页 /403?from
    requireAnyPermission(['task:execute', 'algorithm:read'], location)
  },
  component: StartTestPageRoute,
})
