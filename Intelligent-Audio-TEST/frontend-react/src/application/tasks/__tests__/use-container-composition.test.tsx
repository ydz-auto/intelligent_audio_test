/**
 * 容器判定测试（18_挑选合并功能交互重设计.md §5.5.2 ⑤，INT-1717）。
 * 2026-10-25 docker 网关实测：非容器返 `200 + is_cherry_pick=false + groups=[]`（不再是
 * 400/code:203），故判定必须认 `is_cherry_pick`，否则普通任务详情会误渲染组成区 /
 * 报告卡 / 再次挑选入口。400 / 网络异常仍归一 null → 非容器。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetchTrace: vi.fn() }))

vi.mock('@/application/tasks/use-task-detail', () => ({
  useTaskDetail: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
}))

vi.mock('@/infrastructure/api/cherry-pick-api', () => ({
  // 接线侧 hook 走 Domain 版（INT-1855：DTO/Domain 两个函数并存），两个名字都指向同一 stub
  fetchContainerSourceTrace: (...args: unknown[]) => mocks.fetchTrace(...args),
  fetchContainerSourceTraceDomain: (...args: unknown[]) => mocks.fetchTrace(...args),
}))

import { useContainerComposition } from '@/application/tasks/use-container-composition'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useContainerComposition 容器判定（§5.5.2 ⑤）', () => {
  it('200 + is_cherry_pick=true → 容器（groups 空也按容器走「无来源」空态）', async () => {
    mocks.fetchTrace.mockResolvedValue({
      taskId: 611,
      isCherryPick: true,
      total: 0,
      groups: [],
    })
    const { result } = renderHook(() => useContainerComposition(611), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isContainer).toBe(true)
  })

  it('200 + is_cherry_pick=false + groups=[] → 非容器（普通任务静默）', async () => {
    mocks.fetchTrace.mockResolvedValue({
      taskId: 419,
      isCherryPick: false,
      total: 0,
      groups: [],
    })
    const { result } = renderHook(() => useContainerComposition(419), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isContainer).toBe(false)
  })

  it('非 200（归一 null）→ 非容器', async () => {
    mocks.fetchTrace.mockResolvedValue(null)
    const { result } = renderHook(() => useContainerComposition(419), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isContainer).toBe(false)
  })
})
