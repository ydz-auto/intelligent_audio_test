/**
 * 用例批量入口空选集守卫测试（INT-1780 P3）：
 * 分组卡收起时组内用例尚未懒加载，组头「批量修改」九项 +「删除用例」拿到的 ids 恒为空。
 * 旧实现照样打开弹窗、按 0 条发 POST /testcases/batch 并提示成功（误导性成功）。
 * 现口径：openBatch / handleConfirm 在空 ids 入口拦截——不开弹窗、不发请求、不提示成功，
 * 只给「请先展开分组或勾选用例」提示；非空 ids 路径不受影响。
 *
 * INT-1781：删除分组后的筛选同步（chip 回落「全部」但列表仍按已删 id 查询的根因修复）。
 * - clearDeletedGroupFilter：删的正是当前筛选分组才清空 groupId；按 id 比对，同名分组不误清。
 * - useCaseBatchActions delete-group 成功分支：回调页面 + 失效 ['testcase-groups'] /
 *   ['testcase-group-cases']（INT-1284 独立前缀）；接口失败不回调、不清勾选。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { BatchActionKey } from '@/features/testcases/components/case-bulk-actions'

const batchTestcaseAction = vi.hoisted(() => vi.fn())
const purgeTestcases = vi.hoisted(() => vi.fn())
const deleteTestCase = vi.hoisted(() => vi.fn())
const purgeTestCase = vi.hoisted(() => vi.fn())
const restoreTestCase = vi.hoisted(() => vi.fn())
const deleteGroupMock = vi.hoisted(() => vi.fn())

vi.mock('sonner', () => ({
  toast: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))
vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction,
  purgeTestcases,
  fetchRefreshTaskStatus: vi.fn(),
}))
vi.mock('@/infrastructure/api/testcases-api', () => ({
  deleteTestCase,
  purgeTestCase,
  restoreTestCase,
}))
vi.mock('@/infrastructure/api/groups-api', () => ({
  deleteGroup: deleteGroupMock,
}))

const { useCaseBatchActions, clearDeletedGroupFilter, EMPTY_SELECTION_HINT } =
  await import('../use-case-batch-actions')

/** 组头「批量修改」九项 + 批量浮条其余四项（copy/delete/restore/purge） */
const ALL_BATCH_KEYS: BatchActionKey[] = [
  'params',
  'device',
  'spl',
  'group',
  'dimensions',
  'noise',
  'name',
  'tags',
  'refresh',
  'copy',
  'delete',
  'restore',
  'purge',
]

function renderBatch() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const onClearSelection = vi.fn()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const view = renderHook(() => useCaseBatchActions({ onClearSelection }), { wrapper })
  return { ...view, onClearSelection }
}

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

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useCaseBatchActions 空选集守卫（INT-1780）', () => {
  it.each(ALL_BATCH_KEYS)('%s：空 ids 不开弹窗/不发成功提示，只给提示', (key) => {
    const { result } = renderBatch()

    act(() => result.current.openBatch(key, []))

    expect(result.current.batchDialog).toBeNull()
    expect(result.current.confirm).toBeNull()
    expect(result.current.isBatchOpen).toBe(false)
    expect(toast.warning).toHaveBeenCalledWith(EMPTY_SELECTION_HINT)
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('非空 ids 仍按原路径开弹窗（七件套）与确认（复制/删除等）', () => {
    const { result } = renderBatch()

    act(() => result.current.openBatch('group', ['tc-1', 'tc-2']))
    expect(result.current.batchDialog).toEqual({
      kind: 'group',
      count: 2,
      ids: ['tc-1', 'tc-2'],
    })

    act(() => result.current.openBatch('delete', ['tc-1']))
    expect(result.current.confirm).toEqual({
      kind: 'batch-delete',
      count: 1,
      ids: ['tc-1'],
    })
  })

  it('handleConfirm 空 ids 兜底：不发请求、不按成功提示，并关闭确认态', async () => {
    const { result, onClearSelection } = renderBatch()

    act(() => {
      result.current.setConfirm({ kind: 'batch-delete', count: 0, ids: [] })
    })
    await act(async () => {
      await result.current.handleConfirm({ kind: 'batch-delete', count: 0, ids: [] })
    })

    expect(batchTestcaseAction).not.toHaveBeenCalled()
    expect(purgeTestcases).not.toHaveBeenCalled()
    expect(toast.warning).toHaveBeenCalledWith(EMPTY_SELECTION_HINT)
    expect(toast.success).not.toHaveBeenCalled()
    expect(result.current.confirm).toBeNull()
    expect(onClearSelection).not.toHaveBeenCalled()
  })

  it('handleConfirm 非空 ids 正常发批量请求（守卫不误伤有效提交）', async () => {
    const { result } = renderBatch()
    batchTestcaseAction.mockResolvedValueOnce({})

    await act(async () => {
      await result.current.handleConfirm({ kind: 'batch-delete', count: 1, ids: ['tc-9'] })
    })

    expect(batchTestcaseAction).toHaveBeenCalledWith('delete', ['tc-9'], {})
    expect(toast.success).toHaveBeenCalled()
  })
})

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
