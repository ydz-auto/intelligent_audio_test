import { createFileRoute, redirect, useNavigate, useSearch } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { TestExecutionPage } from '@/features/test-execution'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

/**
 * 开始测试 /start-test（INT-486 合并入口：端到端+API 合并单入口，内部两模式）。
 * 10_测试执行.md §3.1.1/§3.2；不再有「选择算法」步骤（算法切换已全局化 INT-436/442）。
 * beforeLoad 守卫分支：持有 task:execute 走完整交互态；algo_engineer（无 task:execute、
 * 按 INT-449 只读权限点以 algorithm:read 标识）走只读观察态，URL 直达不再 /403；
 * 其余无权限角色（device_admin/guest）仍整页 /403。
 * validateSearch：mode（e2e/api，zod 白名单 catch 'e2e'）+ step（0-3 白名单 catch 0）
 * + view（表格/卡片，zod .catch('table')）。
 */
export const startTestSearchSchema = z
  .object({
    mode: z.enum(['e2e', 'api']).catch('e2e'),
    step: z.coerce.number().int().min(0).max(3).catch(0),
    view: z.enum(['table', 'card']).catch('table'),
  })
  .partial()
  .catch({})

function StartTestPageRoute() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as unknown as {
    mode?: 'e2e' | 'api'
    step?: number
    view?: 'table' | 'card'
  }
  const mode = search.mode ?? 'e2e'
  return (
    <TestExecutionPage
      testType={mode}
      onModeChange={(next) => navigateWithSearch(navigate, { mode: next, step: 0 })}
      initialView={search.view ?? 'table'}
      onViewChange={(view) => navigateWithSearch(navigate, { view })}
    />
  )
}

export const Route = createFileRoute('/_authenticated/start-test')({
  validateSearch: startTestSearchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (hasPermission(user, 'task:execute')) return
    if (hasPermission(user, 'algorithm:read')) return
    throw redirect({ to: '/403' })
  },
  component: StartTestPageRoute,
})
