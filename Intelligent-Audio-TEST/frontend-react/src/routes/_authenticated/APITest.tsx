import { createFileRoute, redirect, useNavigate, useSearch } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { TestExecutionPage } from '@/features/test-execution'
import { testExecutionSearchSchema } from '@/routes/_authenticated/E2ETest'
import { navigateWithSearch } from '@/features/test-execution/lib/navigate-search'

/**
 * API 测试 /APITest（INT-473；10_测试执行.md §3.1.1/§3.2）。
 * 与 /E2ETest 同一组件树（testType='api' 分叉）；守卫/validateSearch 同源
 * （testExecutionSearchSchema 复用）。
 */
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

export const Route = createFileRoute('/_authenticated/APITest')({
  validateSearch: testExecutionSearchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (hasPermission(user, 'task:execute')) return
    if (hasPermission(user, 'algorithm:read')) return
    throw redirect({ to: '/403' })
  },
  component: () => <TestExecutionPageRoute testType='api' />,
})
