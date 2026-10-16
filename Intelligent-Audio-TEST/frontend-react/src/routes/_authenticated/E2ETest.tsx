import { createFileRoute, redirect, useNavigate, useSearch } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { TestExecutionPage } from '@/features/test-execution'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

/**
 * 端到端测试 /E2ETest（INT-473；10_测试执行.md §3.1.1/§3.2）。
 * beforeLoad 守卫分支：持有 task:execute 走完整交互态；algo_engineer（无 task:execute、
 * 按 INT-449 只读权限点以 algorithm:read 标识）走只读观察态，URL 直达不再 /403；
 * 其余无权限角色（device_admin/guest）仍整页 /403。
 * validateSearch：step（0-4 zod 白名单 catch 0）+ view（表格/卡片，zod .catch('table')）。
 */
export const testExecutionSearchSchema = z
  .object({
    step: z.coerce.number().int().min(0).max(4).catch(0),
    view: z.enum(['table', 'card']).catch('table'),
  })
  .partial()
  .catch({})

function TestExecutionPageRoute({ testType }: { testType: 'e2e' | 'api' }) {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as unknown as {
    step?: number
    view?: 'table' | 'card'
  }
  return (
    <TestExecutionPage
      testType={testType}
      initialView={search.view ?? 'table'}
      onViewChange={(view) => navigateWithSearch(navigate, { view })}
    />
  )
}

export const Route = createFileRoute('/_authenticated/E2ETest')({
  validateSearch: testExecutionSearchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (hasPermission(user, 'task:execute')) return
    if (hasPermission(user, 'algorithm:read')) return
    throw redirect({ to: '/403' })
  },
  component: () => <TestExecutionPageRoute testType='e2e' />,
})
