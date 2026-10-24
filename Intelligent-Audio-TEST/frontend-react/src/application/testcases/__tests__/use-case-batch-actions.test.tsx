/**
 * 用例批量入口空选集守卫测试（INT-1780 P3）：
 * 分组卡收起时组内用例尚未懒加载，组头「批量修改」九项 +「删除用例」拿到的 ids 恒为空。
 * 旧实现照样打开弹窗、按 0 条发 POST /testcases/batch 并提示成功（误导性成功）。
 * 现口径：openBatch / handleConfirm 在空 ids 入口拦截——不开弹窗、不发请求、不提示成功，
 * 只给「请先展开分组或勾选用例」提示；非空 ids 路径不受影响。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  EMPTY_SELECTION_HINT,
  useCaseBatchActions,
} from '@/application/testcases/use-case-batch-actions'
import type { BatchActionKey } from '@/features/testcases/components/case-bulk-actions'

const batchTestcaseAction = vi.hoisted(() => vi.fn())
const purgeTestcases = vi.hoisted(() => vi.fn())
const deleteTestCase = vi.hoisted(() => vi.fn())
const purgeTestCase = vi.hoisted(() => vi.fn())
const restoreTestCase = vi.hoisted(() => vi.fn())
const deleteGroup = vi.hoisted(() => vi.fn())

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
vi.mock('@/infrastructure/api/groups-api', () => ({ deleteGroup }))

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
