/**
 * 批量弹窗「轮次范围」真实轮次测试（INT-1731）：
 * 专属参数/播放设备/声压/噪声四窗「指定轮次」网格与「逐轮设置」Tab 均按选中用例真实轮次渲染
 * （多选取最大轮次，未知回落 1，不再是写死的 4 轮）；指定轮次只提交真实存在的轮次，
 * 空勾选不提交（后端对不存在轮次静默回成功）。
 */
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BatchNoiseDialog } from '@/features/testcases/modals/batch-noise-dialog'
import { BatchSplDialog } from '@/features/testcases/modals/batch-spl-dialog'
import { BatchDeviceDialog } from '@/features/testcases/modals/batch-device-dialog'
import { BatchAlgoParamsDialog } from '@/features/testcases/modals/batch-algo-params-dialog'
import { existingRounds } from '@/features/testcases/modals/batch-shared'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

vi.mock('@/infrastructure/api/playback-api', () => ({
  fetchRealPlaybackDevices: vi.fn().mockResolvedValue([]),
  scanRealPlaybackDevices: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/infrastructure/api/audio-list-api', () => ({
  fetchRealAudios: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))

vi.mock('@/application/hooks/use-algorithm-options', () => ({
  useAlgorithmOptions: () => ({ options: [], isLoading: false }),
}))

vi.mock('@/infrastructure/api/algorithm-form-api', () => ({
  fetchAlgorithmFormSchema: vi.fn().mockResolvedValue({ fields: [], groups: [] }),
}))

const mockedBatch = vi.mocked(batchTestcaseAction)

/** 弹窗内 query 调用（播放设备/噪声音频）需要 QueryClient */
const renderWithProviders = (ui: ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/** 四个轮次范围批量窗（name = RoundScopeThreeField 的 name 前缀，用于定位指定轮次网格） */
const DIALOGS = [
  {
    key: 'params',
    name: 'batch-algo-params-round',
    render: () => (
      <BatchAlgoParamsDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} roundCount={2} />
    ),
  },
  {
    key: 'device',
    name: 'batch-device-round',
    render: () => (
      <BatchDeviceDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} roundCount={2} />
    ),
  },
  {
    key: 'spl',
    name: 'batch-spl-round',
    render: () => (
      <BatchSplDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} roundCount={2} />
    ),
  },
  {
    key: 'noise',
    name: 'batch-noise-round',
    render: () => (
      <BatchNoiseDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} roundCount={2} />
    ),
  },
] as const

describe('existingRounds（真实轮次收敛）', () => {
  it('丢弃不存在/非法轮次并去重排序', () => {
    expect(existingRounds([1, 3, 5], 2)).toEqual([1])
    expect(existingRounds([2, 1, 2], 4)).toEqual([1, 2])
    expect(existingRounds([0, -1, 1.5, 2], 2)).toEqual([2])
    expect(existingRounds([], 2)).toEqual([])
  })

  it('未知轮次回落 1（不大于 0 的入参按 1 处理）', () => {
    expect(existingRounds([1, 2], 0)).toEqual([1])
  })
})

describe.each(DIALOGS)('$key 批量窗轮次范围按选中用例真实轮次渲染（INT-1731）', ({ name, render: renderDialog }) => {
  beforeEach(() => {
    mockedBatch.mockReset()
    mockedBatch.mockResolvedValue({ updatedCount: 2 })
  })

  it('指定轮次网格只出真实轮次（2 轮用例不出第 3/4 轮）', async () => {
    const user = userEvent.setup()
    renderWithProviders(renderDialog())
    await user.click(screen.getByText('指定轮次（统一设置）'))
    const grid = within(screen.getByTestId(`${name}-specific-rounds`))
    expect(grid.getByText('第1轮')).toBeInTheDocument()
    expect(grid.getByText('第2轮')).toBeInTheDocument()
    expect(grid.queryByText('第3轮')).not.toBeInTheDocument()
    expect(grid.queryByText('第4轮')).not.toBeInTheDocument()
  })

  it('逐轮设置 Tab 同口径（第 1/2 轮，无第 3/4 轮）', async () => {
    const user = userEvent.setup()
    renderWithProviders(renderDialog())
    await user.click(screen.getByText('逐轮设置（每轮可不同）'))
    expect(screen.getByRole('button', { name: '第1轮' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第2轮' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '第3轮' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '第4轮' })).not.toBeInTheDocument()
  })
})

describe('批量设置声压级：提交轮次收口（INT-1731）', () => {
  beforeEach(() => {
    mockedBatch.mockReset()
    mockedBatch.mockResolvedValue({ updatedCount: 2 })
  })

  it('指定轮次只提交真实存在的轮次号', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <BatchSplDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} roundCount={2} />
    )
    await user.type(screen.getByLabelText('声压级 dB'), '88')
    await user.click(screen.getByText('指定轮次（统一设置）'))
    await user.click(screen.getByRole('button', { name: '确定' }))

    expect(mockedBatch).toHaveBeenCalledTimes(1)
    const [action, , payload = {}] = mockedBatch.mock.calls[0]
    expect(action).toBe('update_spl')
    expect(payload.roundMode).toBe('specific')
    expect(payload.roundNumbers).toEqual([1])
  })

  it('指定轮次一个都没勾：不提交并提示（不静默回成功）', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <BatchSplDialog open onOpenChange={vi.fn()} count={2} ids={['tc-1', 'tc-2']} roundCount={2} />
    )
    await user.type(screen.getByLabelText('声压级 dB'), '88')
    await user.click(screen.getByText('指定轮次（统一设置）'))
    // 取消默认勾选的第 1 轮 → 空集
    const grid = within(screen.getByTestId('batch-spl-round-specific-rounds'))
    await user.click(grid.getAllByRole('checkbox')[0])
    await user.click(screen.getByRole('button', { name: '确定' }))

    expect(mockedBatch).not.toHaveBeenCalled()
  })
})

describe('轮次范围按传入 roundCount 渲染（1 轮不是 4 轮）', () => {
  it('播放设备窗 roundCount=1：指定轮次只有第 1 轮', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <BatchDeviceDialog open onOpenChange={vi.fn()} count={1} ids={['tc-1']} roundCount={1} />
    )
    await user.click(screen.getByText('指定轮次（统一设置）'))
    const grid = within(screen.getByTestId('batch-device-round-specific-rounds'))
    expect(grid.getByText('第1轮')).toBeInTheDocument()
    expect(grid.queryByText('第2轮')).not.toBeInTheDocument()
  })
})
