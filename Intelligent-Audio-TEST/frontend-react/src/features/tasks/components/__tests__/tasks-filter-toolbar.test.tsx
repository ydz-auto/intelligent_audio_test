/**
 * 任务筛选工具栏「开始挑选」入口 RBAC 测试（18_挑选合并交互重设计.md §3.8.1，INT-1048）：
 * - 日常 tab + task:cherry_pick 权限 → 按钮可见（primary + ShoppingCart）
 * - 日常 tab + 无 task:cherry_pick（如 algo_engineer）→ 按钮隐藏
 * - 非日常页签（已发布）→ 按钮不渲染（入口仅日常 tab）
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TasksFilterToolbar } from '@/features/tasks/components/tasks-filter-toolbar'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { fetchTaskDomainStats } from '@/infrastructure/api/tasks-api'
import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithm-api'
import type { TaskListFilters } from '@/application/tasks/use-tasks-list'

vi.mock('@/infrastructure/api/tasks-api', () => ({
  fetchTaskDomainStats: vi.fn(),
}))

vi.mock('@/infrastructure/api/algorithm-api', () => ({
  fetchAlgorithmOptions: vi.fn(),
}))

function makeUser(permissions: string[]) {
  return {
    id: '1',
    username: 'u',
    displayName: 'u',
    roleName: '',
    permissions,
  }
}

const NOOP = () => undefined

function renderToolbar(tab: 'daily' | 'published', permissions: string[]) {
  useAuthStore.setState({ user: makeUser(permissions) })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const filters: TaskListFilters = { page: 1, pageSize: 10 }
  render(
    <TasksFilterToolbar
      tab={tab}
      filters={filters}
      onChange={NOOP}
      onReset={NOOP}
      onSearch={NOOP}
      isFiltered={false}
      onStartPick={NOOP}
    />,
    { wrapper }
  )
}

describe('TasksFilterToolbar「开始挑选」入口（§3.8.1，INT-1048）', () => {
  beforeEach(() => {
    vi.mocked(fetchTaskDomainStats).mockResolvedValue({
      total: 0,
      status_counts: {},
      deleted_total: 0,
    } as never)
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue([] as never)
  })

  it('日常 tab + task:cherry_pick 权限 → 按钮可见', () => {
    renderToolbar('daily', ['task:read', 'task:cherry_pick'])
    const btn = screen.getByRole('button', { name: '开始挑选' })
    expect(btn).toBeInTheDocument()
  })

  it('日常 tab + 无 task:cherry_pick（algo_engineer 口径）→ 按钮隐藏', () => {
    renderToolbar('daily', ['task:read'])
    expect(screen.queryByRole('button', { name: '开始挑选' })).not.toBeInTheDocument()
  })

  it('已发布页签 → 按钮不渲染（入口仅日常 tab）', () => {
    renderToolbar('published', ['*'])
    expect(screen.queryByRole('button', { name: '开始挑选' })).not.toBeInTheDocument()
  })
})
