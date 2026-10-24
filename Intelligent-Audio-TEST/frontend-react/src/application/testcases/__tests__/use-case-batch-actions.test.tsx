/**
 * INT-1781：删除分组后的筛选同步（chip 回落「全部」但列表仍按已删 id 查询的根因修复）。
 * - clearDeletedGroupFilter：删的正是当前筛选分组才清空 groupId；按 id 比对，同名分组不误清。
 * - useCaseBatchActions delete-group 成功分支：回调页面 + 失效 ['testcase-groups'] /
 *   ['testcase-group-cases']（INT-1284 独立前缀）；接口失败不回调、不清勾选。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const deleteGroupMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/groups-api', () => ({
  deleteGroup: deleteGroupMock,
}))
vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
  fetchRefreshTaskStatus: vi.fn(),
  purgeTestcases: vi.fn(),
}))
vi.mock('@/infrastructure/api/testcases-api', () => ({
  deleteTestCase: vi.fn(),
  purgeTestCase: vi.fn(),
  restoreTestCase: vi.fn(),
}))

const { useCaseBatchActions, clearDeletedGroupFilter } = await import(
  '../use-case-batch-actions'
)

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
  const onClearSelection = vi.fn()
  const onGroupDeleted = vi.fn()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(
    () => useCaseBatchActions({ onClearSelection, onGroupDeleted }),
    { wrapper }
  )
  return { result, onClearSelection, onGroupDeleted, invalidateSpy }
}

describe('clearDeletedGroupFilter（INT-1781）', () => {
  it('删除的正是当前筛选分组 → 清空 groupId，其余筛选保留', () => {
    expect(
      clearDeletedGroupFilter({ groupId: 'g-1', search: '接线测试' }, 'g-1')
    ).toEqual({ groupId: null, search: '接线测试' })
  })

  it('删除的是别的分组 → 原筛选对象不变（同名分组也不误清）', () => {
    const filters = { groupId: 'g-2', tag: '标签A' }
    expect(clearDeletedGroupFilter(filters, 'g-1')).toBe(filters)
  })

  it('没有分组筛选 → 原对象不变', () => {
    const filters = { search: 'abc' }
    expect(clearDeletedGroupFilter(filters, 'g-1')).toBe(filters)
  })
})

describe('useCaseBatchActions delete-group（INT-1781）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    deleteGroupMock.mockResolvedValue(undefined)
  })

  it('删除成功后回调页面、清勾选，并失效分组与分组内懒加载缓存', async () => {
    const { result, onClearSelection, onGroupDeleted, invalidateSpy } = setup()

    await act(async () => {
      await result.current.handleConfirm({
        kind: 'delete-group',
        ids: ['g-1'],
        name: '接线测试_INT1781组',
      })
    })

    expect(deleteGroupMock).toHaveBeenCalledWith('g-1', true)
    expect(onGroupDeleted).toHaveBeenCalledWith('g-1')
    expect(onClearSelection).toHaveBeenCalledTimes(1)
    const keys = invalidateSpy.mock.calls.map(
      (call) => call[0]?.queryKey
    )
    expect(keys).toEqual(
      expect.arrayContaining([
        ['testcases'],
        ['testcase-groups'],
        ['testcase-group-cases'],
      ])
    )
  })

  it('接口失败不触发筛选清理，保留勾选可重试', async () => {
    deleteGroupMock.mockRejectedValueOnce(new Error('删除分组失败'))
    const { result, onClearSelection, onGroupDeleted } = setup()

    await act(async () => {
      await result.current.handleConfirm({
        kind: 'delete-group',
        ids: ['g-1'],
        name: '接线测试_INT1781组',
      })
    })

    expect(deleteGroupMock).toHaveBeenCalledTimes(1)
    expect(onGroupDeleted).not.toHaveBeenCalled()
    expect(onClearSelection).not.toHaveBeenCalled()
  })
})
