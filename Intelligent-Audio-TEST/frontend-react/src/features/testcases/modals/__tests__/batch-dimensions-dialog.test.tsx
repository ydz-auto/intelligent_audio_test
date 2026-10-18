/**
 * 批量设置评估维度弹窗测试（11_用例域.md §5.3.5）：
 * 主/子分组云渲染、逐轮模式快捷操作工具栏三件、多轮整体评估维度节、已选维度权重/阈值参数卡、
 * 提交载荷（统一 dimensions + multi_dimensions；逐轮 round_dimensions + multi_dimensions）。
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MOCK_CASE_DIMENSIONS } from '@/infrastructure/mock/testcases-mock'
import { BatchDimensionsDialog } from '@/features/testcases/modals/batch-dimensions-dialog'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

const mockedBatch = vi.mocked(batchTestcaseAction)

const setup = () => {
  render(
    <BatchDimensionsDialog
      open
      onOpenChange={vi.fn()}
      count={3}
      ids={['tc-1', 'tc-2', 'tc-3']}
      dimensions={MOCK_CASE_DIMENSIONS}
      algorithmType={null}
      testType='e2e'
    />
  )
}

/** 单轮维度选择器（有搜索框） */
const roundCloud = () => within(screen.getByTestId('batch-dim-round-cloud'))
/** 多轮整体评估维度选择器（无搜索框） */
const multiCloud = () => within(screen.getByTestId('batch-dim-multi-cloud'))

const goPerRound = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByText('逐轮设置（每轮可不同）'))
}

describe('BatchDimensionsDialog（§5.3.5）', () => {
  beforeEach(() => {
    mockedBatch.mockReset()
    mockedBatch.mockResolvedValue({ updatedCount: 3 })
  })

  it('维度选择为主/子分组云：主 chip「主」徽章 + 子维度「子」徽章', () => {
    setup()
    expect(roundCloud().getAllByText('主').length).toBeGreaterThanOrEqual(2)
    expect(roundCloud().getAllByText('子').length).toBeGreaterThanOrEqual(2)
    expect(roundCloud().getByText('识别准确率')).toBeInTheDocument()
    expect(roundCloud().getByText('字准率')).toBeInTheDocument()
    expect(roundCloud().getByText('已选 0 项')).toBeInTheDocument()
    // 多轮整体评估维度节独立渲染（无搜索框）
    expect(screen.getByText('多轮整体评估维度（跨轮次聚合）')).toBeInTheDocument()
    expect(multiCloud().getByText('语义理解')).toBeInTheDocument()
  })

  it('点击主维度 chip 联动全部子维度并渲染权重/阈值参数卡', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(roundCloud().getByRole('button', { name: /识别准确率/ }))
    // 联动子维度：已选 3 项（主 1 + 子 11/12）
    expect(roundCloud().getByText('已选 3 项')).toBeInTheDocument()
    // 已选维度参数卡（权重 0-100 默认 50 + 阈值 0-100 默认 80）
    expect(screen.getByText('维度权重和阈值配置')).toBeInTheDocument()
    expect(screen.getAllByDisplayValue('50').length).toBe(3)
    expect(screen.getAllByDisplayValue('80').length).toBe(3)
  })

  it('逐轮模式渲染快捷操作工具栏三件 + 多轮整体评估维度节', async () => {
    const user = userEvent.setup()
    setup()
    await goPerRound(user)
    expect(screen.getByRole('button', { name: /从其他轮次复制/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /清空当前轮次/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /应用到所有轮次/ })).toBeInTheDocument()
    expect(screen.getByText('多轮整体评估维度（跨轮次聚合）')).toBeInTheDocument()
    expect(screen.getByText('可选')).toBeInTheDocument()
  })

  it('提交（统一模式）载荷含 dimensions 权重/阈值 + multi_dimensions', async () => {
    const user = userEvent.setup()
    setup()
    // 单轮选主维度（联动子维度）
    await user.click(roundCloud().getByRole('button', { name: /识别准确率/ }))
    // 多轮整体评估勾选一个维度
    await user.click(multiCloud().getByRole('button', { name: /语义理解/ }))
    await user.click(screen.getByRole('button', { name: '确定' }))

    expect(mockedBatch).toHaveBeenCalledTimes(1)
    const [action, ids, payload = {}] = mockedBatch.mock.calls[0]
    expect(action).toBe('update_dimensions')
    expect(ids).toEqual(['tc-1', 'tc-2', 'tc-3'])
    expect(payload.roundMode).toBe('all')
    expect(payload.dimensions!).toHaveLength(3)
    expect(payload.dimensions![0]).toMatchObject({ id: 1, name: '识别准确率', weight: 50, threshold: 80 })
    // multi_dimensions 恒提交（勾选主维度联动子维度 → 2 项）
    expect(payload.multiDimensions!).toHaveLength(2)
    expect(payload.multiDimensions![0]).toMatchObject({ id: 2, name: '语义理解', weight: 50, threshold: 80 })
    expect(payload.multiDimensions![1]).toMatchObject({ id: 21, name: '指令完成度', weight: 50, threshold: 80 })
  })

  it('提交（逐轮模式）载荷含 round_dimensions + multi_dimensions', async () => {
    const user = userEvent.setup()
    setup()
    await goPerRound(user)
    // 当前轮「第 1 轮」选主维度
    await user.click(roundCloud().getByRole('button', { name: /识别准确率/ }))
    await user.click(screen.getByRole('button', { name: '确定' }))

    expect(mockedBatch).toHaveBeenCalledTimes(1)
    const [action, , payload = {}] = mockedBatch.mock.calls[0]
    expect(action).toBe('update_dimensions')
    expect(payload.roundMode).toBe('per_round')
    expect(payload.roundDimensions).toBeDefined()
    // 轮次 key 为字符串（JSON 序列化口径）
    const rds = payload.roundDimensions as Record<string, unknown[]>
    expect(Object.keys(rds).length).toBeGreaterThanOrEqual(1)
    expect(rds['1']).toHaveLength(3)
    expect(payload.multiDimensions).toEqual([])
  })

  it('逐轮「从其他轮次复制」把源轮次选择复制到当前轮', async () => {
    const user = userEvent.setup()
    setup()
    await goPerRound(user)
    // 第 1 轮选「识别准确率」组
    await user.click(roundCloud().getByRole('button', { name: /识别准确率/ }))
    expect(roundCloud().getByText('已选 3 项')).toBeInTheDocument()
    // 切到第 2 轮（空）
    await user.click(screen.getByRole('button', { name: '第 2 轮' }))
    expect(roundCloud().getByText('已选 0 项')).toBeInTheDocument()
    // 从其他轮次复制（源默认第 1 轮）
    await user.click(screen.getByRole('button', { name: /从其他轮次复制/ }))
    const popover = within(screen.getByTestId('batch-dim-copy-source'))
    await user.click(popover.getByRole('button', { name: '确定' }))
    expect(roundCloud().getByText('已选 3 项')).toBeInTheDocument()
  })

  it('逐轮模式停留在默认第 1 轮时，「从其他轮次复制」源默认为首个其他轮次（第 2 轮）而非自身', async () => {
    const user = userEvent.setup()
    setup()
    await goPerRound(user)
    // 保持默认第 1 轮，打开复制弹窗
    await user.click(screen.getByRole('button', { name: /从其他轮次复制/ }))
    const popover = within(screen.getByTestId('batch-dim-copy-source'))
    // 源 Select 默认「第 2 轮」（首个其他轮次），不显示自身「第 1 轮」为源
    expect(popover.getByText('第 2 轮')).toBeInTheDocument()
    expect(popover.queryByText('第 1 轮')).not.toBeInTheDocument()
    // 复制到第 1 轮确认后仍为空（第 2 轮未配置，复制空选择）
    await user.click(popover.getByRole('button', { name: '确定' }))
    expect(roundCloud().getByText('已选 0 项')).toBeInTheDocument()
  })
})
