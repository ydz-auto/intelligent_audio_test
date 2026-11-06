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

const setup = (roundCount = 4, unknownRoundCount = 0) => {
  render(
    <BatchDimensionsDialog
      open
      onOpenChange={vi.fn()}
      count={3}
      ids={['tc-1', 'tc-2', 'tc-3']}
      roundCount={roundCount}
      unknownRoundCount={unknownRoundCount}
      dimensions={MOCK_CASE_DIMENSIONS}
      algorithmType={null}
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

  it('「指定轮次」网格按选中用例真实轮次数渲染（INT-1642：不再是固定 4 轮）', async () => {
    const user = userEvent.setup()
    render(
      <BatchDimensionsDialog
        open
        onOpenChange={vi.fn()}
        count={2}
        ids={['tc-1', 'tc-2']}
        dimensions={MOCK_CASE_DIMENSIONS}
        roundCount={2}
      />
    )
    await user.click(screen.getByText('指定轮次（统一设置）'))
    expect(screen.getByText('第1轮')).toBeInTheDocument()
    expect(screen.getByText('第2轮')).toBeInTheDocument()
    expect(screen.queryByText('第3轮')).not.toBeInTheDocument()
    expect(screen.queryByText('第4轮')).not.toBeInTheDocument()

    // 逐轮 Tab 同口径：按真实轮次逐个展开，不额外合成「最后一轮」页签（INT-1506）
    await user.click(screen.getByText('逐轮设置（每轮可不同）'))
    expect(screen.getByRole('button', { name: '第 1 轮' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第 2 轮' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '最后一轮' })).not.toBeInTheDocument()
  })

  it('单轮用例：指定轮次只有第 1 轮，逐轮 Tab 无「最后一轮」重复项', async () => {
    const user = userEvent.setup()
    render(
      <BatchDimensionsDialog
        open
        onOpenChange={vi.fn()}
        count={1}
        ids={['tc-1']}
        dimensions={MOCK_CASE_DIMENSIONS}
        roundCount={1}
      />
    )
    await user.click(screen.getByText('指定轮次（统一设置）'))
    expect(screen.getByText('第1轮')).toBeInTheDocument()
    expect(screen.queryByText('第2轮')).not.toBeInTheDocument()
    await user.click(screen.getByText('逐轮设置（每轮可不同）'))
    expect(screen.getByRole('button', { name: '第 1 轮' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '最后一轮' })).not.toBeInTheDocument()
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

  it('逐轮 Tab 按选中用例实际轮次渲染（2 轮用例不出第 3 轮，添加轮次禁用）', async () => {
    const user = userEvent.setup()
    setup(2)
    await goPerRound(user)
    expect(screen.getByRole('button', { name: '第 1 轮' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第 2 轮' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '第 3 轮' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /添加轮次/ })).toBeDisabled()
  })

  it('无轮次信息时给空态并禁用确定', async () => {
    const user = userEvent.setup()
    setup(0)
    expect(screen.getAllByText('所选用例暂无可配置的轮次信息').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('button', { name: '确定' })).toBeDisabled()
    // 指定轮次同样空态，不渲染轮次勾选
    await user.click(screen.getByText('指定轮次（统一设置）'))
    expect(screen.queryByText('第1轮')).not.toBeInTheDocument()
  })

  it('轮次未知（用例未加载）不算无轮次：显式提示、按所有轮次选中的维度真的进载荷', async () => {
    const user = userEvent.setup()
    setup(0, 2)
    // 不再是「暂无可配置的轮次信息」假空态
    expect(screen.queryByText('所选用例暂无可配置的轮次信息')).not.toBeInTheDocument()
    expect(screen.getAllByText(/其中 2 个用例的轮次信息尚未加载/).length).toBeGreaterThanOrEqual(1)
    // 没有已知轮次：按轮次的两档禁用，但「所有轮次（统一设置）」可提交
    expect(screen.getByRole('radio', { name: '指定轮次（统一设置）' })).toBeDisabled()
    expect(screen.getByRole('radio', { name: '逐轮设置（每轮可不同）' })).toBeDisabled()
    const ok = screen.getByRole('button', { name: '确定' })
    expect(ok).toBeEnabled()
    // 轮次未知时点维度必须真的勾上（哨兵键承载），不能是空操作
    await user.click(roundCloud().getByRole('button', { name: /识别准确率/ }))
    expect(roundCloud().getByText('已选 3 项')).toBeInTheDocument()
    expect(screen.getByText('维度权重和阈值配置')).toBeInTheDocument()
    await user.click(ok)
    expect(mockedBatch).toHaveBeenCalledTimes(1)
    const [action, , payload = {}] = mockedBatch.mock.calls[0]
    expect(action).toBe('update_dimensions')
    expect(payload.roundMode).toBe('all')
    // 关键：选中的维度必须进载荷（空数组=后端清空，不可撤销）
    expect(payload.dimensions!).toHaveLength(3)
    expect(payload.dimensions![0]).toMatchObject({ id: 1, name: '识别准确率', weight: 50, threshold: 80 })
    expect(payload.multiDimensions).toEqual([])
  })

  it('统一模式未选任何维度点确定：先二次确认，确认后才发清空载荷', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: '确定' }))
    // 未确认前不提交
    expect(mockedBatch).not.toHaveBeenCalled()
    expect(screen.getByText('确定清空所选用例的评估维度？')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确定清空' }))
    expect(mockedBatch).toHaveBeenCalledTimes(1)
    const [, , payload = {}] = mockedBatch.mock.calls[0]
    expect(payload.dimensions).toEqual([])
  })
})
