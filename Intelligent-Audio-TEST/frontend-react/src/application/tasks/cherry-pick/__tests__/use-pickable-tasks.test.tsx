/**
 * 挑选向导阶段 1 数据源接线（INT-1509 / INT-1496 §8.1）：
 * - usePickableTasks 只打 pickable-tasks，排序切换换参数重取（服务端排序取代客户端权重排序）
 * - 「来源任务」筛选与清单同源（pickable-tasks），设备/结果类型仍走阶段 2 candidates facet
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  PickableTask,
  PickableTaskSortBy,
  PickableTaskSortOrder,
} from '@/domain/models/cherryPick'

const fetchAllPickableTasksMock = vi.hoisted(() => vi.fn())
const fetchPickableTaskOptionsMock = vi.hoisted(() => vi.fn())
const fetchCherryPickCandidateTreeMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/cherry-pick-api', () => ({
  fetchAllPickableTasks: fetchAllPickableTasksMock,
  fetchPickableTaskOptions: fetchPickableTaskOptionsMock,
  fetchCherryPickCandidateTree: fetchCherryPickCandidateTreeMock,
}))

const { usePickableTasks, usePickFilterOptions } = await import('../use-cherry-pick-candidates')

function task(taskId: number, taskName: string, count: number): PickableTask {
  return {
    taskId,
    taskName,
    executionStatus: 'completed',
    createdAt: '2026-10-21T09:00:00',
    count,
  }
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('usePickableTasks（阶段 1 数据源）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchAllPickableTasksMock.mockResolvedValue({
      items: [task(419, '任务419', 138), task(418, '任务418', 62)],
      total: 117,
    })
  })

  it('按服务端排序参数取数，透出 items 与 total', async () => {
    const { result } = renderHook(
      () =>
        usePickableTasks({
          sortBy: 'status' as PickableTaskSortBy,
          sortOrder: 'asc' as PickableTaskSortOrder,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(fetchAllPickableTasksMock).toHaveBeenCalledWith({
      sortBy: 'status',
      sortOrder: 'asc',
    })
    expect(result.current.items.map((t) => t.taskId)).toEqual([419, 418])
    expect(result.current.total).toBe(117)
    expect(result.current.isError).toBe(false)
  })

  it('切换排序键/方向 → 以新参数重取（排序由服务端完成）', async () => {
    const { result, rerender } = renderHook(
      ({ sortBy, sortOrder }: { sortBy: PickableTaskSortBy; sortOrder: PickableTaskSortOrder }) =>
        usePickableTasks({ sortBy, sortOrder }),
      {
        wrapper: createWrapper(),
        initialProps: { sortBy: 'status' as PickableTaskSortBy, sortOrder: 'asc' as PickableTaskSortOrder },
      }
    )
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    rerender({ sortBy: 'created_at' as PickableTaskSortBy, sortOrder: 'desc' as PickableTaskSortOrder })
    await waitFor(() =>
      expect(fetchAllPickableTasksMock).toHaveBeenLastCalledWith({
        sortBy: 'created_at',
        sortOrder: 'desc',
      })
    )
    expect(fetchAllPickableTasksMock).toHaveBeenCalledTimes(2)
  })

  it('接口失败 → isError，供阶段 1 错误态重试', async () => {
    fetchAllPickableTasksMock.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(
      () =>
        usePickableTasks({
          sortBy: 'status' as PickableTaskSortBy,
          sortOrder: 'asc' as PickableTaskSortOrder,
        }),
      { wrapper: createWrapper() }
    )
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.items).toEqual([])
  })
})

describe('usePickFilterOptions（选项全部来自真实数据源）', () => {
  const tree = {
    total: 2,
    taskCount: 1,
    meta: {
      tasks: [{ taskId: 419, taskName: '任务419', taskStatus: 'completed' }],
      cases: [],
      devices: [
        { deviceId: 1, deviceName: null },
        { deviceId: 9, deviceName: 'pura90小艺' },
      ],
      apis: [{ apiId: 7, apiName: 'ASR-API' }],
    },
    tree: [
      {
        taskId: 419,
        count: 2,
        cases: [
          {
            caseId: 'c1',
            count: 2,
            devices: [
              {
                deviceId: 1,
                apiId: null,
                count: 2,
                resultTypes: [
                  { resultType: 'default', count: 2, resultIds: [1, 2] },
                ],
              },
            ],
          },
        ],
      },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    fetchPickableTaskOptionsMock.mockResolvedValue([{ id: 419, name: '任务419' }])
  })

  it('来源任务来自 pickable-tasks，设备/API/结果类型从候选树 meta 派生，阶段 1 不再调树端点', async () => {
    const { result } = renderHook(() => usePickFilterOptions(true, tree), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.tasks).toHaveLength(1))
    expect(result.current.tasks).toEqual([{ id: 419, name: '任务419' }])
    expect(result.current.devices).toEqual([
      { id: 1, name: '设备 1' },
      { id: 9, name: 'pura90小艺' },
    ])
    expect(result.current.apis).toEqual([{ id: 7, name: 'ASR-API' }])
    // 缺值桶显示「结果类型待补充」，值仍是 default（服务端过滤取值）
    expect(result.current.resultTypes).toEqual([
      { value: 'default', label: '结果类型待补充' },
    ])
    expect(fetchPickableTaskOptionsMock).toHaveBeenCalledTimes(1)
  })

  it('阶段 1（enabled=false）不拉来源任务选项', () => {
    renderHook(() => usePickFilterOptions(false, undefined), {
      wrapper: createWrapper(),
    })
    expect(fetchPickableTaskOptionsMock).not.toHaveBeenCalled()
  })
})
