/**
 * 日志标记结果提示（INT-1945）。
 * 文件日志游标行（id ≥ 10^12，审计 JSONL）后端只读：PUT /logs/mark 返回 200 +
 * data.updated=0 +「所选为文件日志，不支持标记（仅历史库行可标记）」。
 * 旧实现 onSuccess 无条件 toast.success('日志已标记') → 行内无徽标、未落库却报成功。
 * 现口径：按 updated（缺失时按请求里的历史库行数）区分全部不可标记 / 部分 / 全部成功；
 * 未落库不刷新列表；旧包不返 data 时不能把成功当成失败。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const markLogs = vi.hoisted(() => vi.fn())

vi.mock('sonner', () => ({
  toast: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))
vi.mock('@/infrastructure/api/logsApi', () => ({
  markLogs,
  clearLogs: vi.fn(),
  exportLogs: vi.fn(),
  LOG_LIST_QUERY_KEY: ['logs', 'list'],
  LOG_STATS_QUERY_KEY: ['logs', 'stats'],
}))

const { LOG_MARK_FILE_ONLY_HINT, logMarkResultToast, resolveMarkedCount, useLogMutations } =
  await import('../useLogMutations')

const FILE_ID = 1792958227144761 // 审计文件游标行（≥ 10^12，只读）
const LEGACY_ID = 6849626 // 历史 logs 表行（可标记）

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useLogMutations(), { wrapper })
  return { result, invalidateSpy }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('logMarkResultToast', () => {
  it('纯文件日志 updated=0 → 提示不可标记，不报成功', () => {
    expect(logMarkResultToast([FILE_ID], 0)).toEqual({
      level: 'warning',
      message: LOG_MARK_FILE_ONLY_HINT,
    })
  })

  it('旧包不返 data（updated=null）且全为文件日志 → 仍提示不可标记', () => {
    expect(logMarkResultToast([FILE_ID], null)).toEqual({
      level: 'warning',
      message: LOG_MARK_FILE_ONLY_HINT,
    })
  })

  it('部分文件日志 updated=1 → 只报实际标记条数并说明不可标记条数', () => {
    expect(logMarkResultToast([LEGACY_ID, FILE_ID], 1)).toEqual({
      level: 'warning',
      message: '已标记 1 条；1 条为文件日志，不支持标记',
    })
  })

  it('旧包 updated=null 的混合批次 → 按历史库行数推定部分成功', () => {
    expect(logMarkResultToast([LEGACY_ID, FILE_ID], null)).toEqual({
      level: 'warning',
      message: '已标记 1 条；1 条为文件日志，不支持标记',
    })
  })

  it('全部历史库行 → 成功文案不变', () => {
    expect(logMarkResultToast([LEGACY_ID], 1)).toEqual({
      level: 'success',
      message: '日志已标记',
    })
  })

  it('旧包 updated=null 的历史库行 → 仍按成功（不能把无 data 当失败）', () => {
    expect(logMarkResultToast([LEGACY_ID], null)).toEqual({
      level: 'success',
      message: '日志已标记',
    })
  })

  it('历史库行 updated=0（行已不存在）→ 明确未标记，不报成功', () => {
    expect(logMarkResultToast([LEGACY_ID], 0)).toEqual({
      level: 'error',
      message: '未标记任何日志，请刷新后重试',
    })
  })
})

describe('resolveMarkedCount', () => {
  it('后端 updated 优先', () => {
    expect(resolveMarkedCount({ updated: 2 }, [FILE_ID, LEGACY_ID])).toBe(2)
  })

  it('无 data 时按请求里的历史库行数推定', () => {
    expect(resolveMarkedCount({ updated: null }, [FILE_ID, LEGACY_ID])).toBe(1)
  })
})

describe('useLogMutations.mark（INT-1945）', () => {
  it('文件日志行 updated=0：toast.warning，不 toast.success，不刷新列表', async () => {
    const { result, invalidateSpy } = setup()
    markLogs.mockResolvedValueOnce({ updated: 0 })

    await act(async () => {
      await result.current.mark.mutateAsync({ logIds: [FILE_ID], mark: 'yellow' })
    })

    expect(markLogs).toHaveBeenCalledWith({ logIds: [FILE_ID], mark: 'yellow' })
    expect(toast.warning).toHaveBeenCalledWith(LOG_MARK_FILE_ONLY_HINT)
    expect(toast.success).not.toHaveBeenCalled()
    expect(invalidateSpy).not.toHaveBeenCalled()
  })

  it('历史库行 updated=1：toast.success + 刷新列表', async () => {
    const { result, invalidateSpy } = setup()
    markLogs.mockResolvedValueOnce({ updated: 1 })

    await act(async () => {
      await result.current.mark.mutateAsync({ logIds: [LEGACY_ID], mark: 'red' })
    })

    expect(toast.success).toHaveBeenCalledWith('日志已标记')
    expect(toast.warning).not.toHaveBeenCalled()
    expect(invalidateSpy).toHaveBeenCalled()
  })

  it('旧包不返 data（updated=null）：历史库行仍成功并刷新列表', async () => {
    const { result, invalidateSpy } = setup()
    markLogs.mockResolvedValueOnce({ updated: null })

    await act(async () => {
      await result.current.mark.mutateAsync({ logIds: [LEGACY_ID], mark: 'red' })
    })

    expect(toast.success).toHaveBeenCalledWith('日志已标记')
    expect(invalidateSpy).toHaveBeenCalled()
  })

  it('混合批次：warning 说明部分不可标记，仍刷新列表', async () => {
    const { result, invalidateSpy } = setup()
    markLogs.mockResolvedValueOnce({ updated: 1 })

    await act(async () => {
      await result.current.mark.mutateAsync({ logIds: [LEGACY_ID, FILE_ID], mark: 'green' })
    })

    expect(toast.warning).toHaveBeenCalledWith('已标记 1 条；1 条为文件日志，不支持标记')
    expect(toast.success).not.toHaveBeenCalled()
    expect(invalidateSpy).toHaveBeenCalled()
  })

  it('接口失败仍走错误提示', async () => {
    const { result } = setup()
    markLogs.mockRejectedValueOnce(new Error('boom'))

    await act(async () => {
      await result.current.mark
        .mutateAsync({ logIds: [LEGACY_ID], mark: 'blue' })
        .catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('标记失败，请稍后重试')
    expect(toast.success).not.toHaveBeenCalled()
  })
})
