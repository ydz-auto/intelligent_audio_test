/**
 * 批量调整分组弹窗 Select 闭合态显示测试（INT-1686 P2）：
 * 选完目标分组后触发器应显示分组名，而不是原始分组 id（base-ui Select 未传 items
 * 时闭合态回退 stringify 原始 value）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import { BatchAdjustGroupDialog } from '@/features/testcases/modals/batch-adjust-group-dialog'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'

vi.mock('@/infrastructure/api/groups-api', () => ({ createGroup: vi.fn() }))
vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

const GROUP_ID = '31d8cb2d-b349-4187-b7e0-d3f7cadc0d26'
const GROUPS: TestCaseGroup[] = [
  {
    id: GROUP_ID,
    name: '接线测试_分组A',
    description: null,
    algorithmType: null,
    createdAt: '2026-10-24T00:00:00Z',
    updatedAt: '2026-10-24T00:00:00Z',
    testCaseCount: 0,
  },
]

const setup = () =>
  render(
    <BatchAdjustGroupDialog
      open
      onOpenChange={vi.fn()}
      count={2}
      ids={['tc-1', 'tc-2']}
      groups={GROUPS}
    />
  )

describe('BatchAdjustGroupDialog 目标分组 Select（INT-1686 P2）', () => {
  it('选完分组后触发器显示分组名，不显示分组 id', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: '接线测试_分组A' }))

    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveTextContent('接线测试_分组A')
    expect(trigger).not.toHaveTextContent(GROUP_ID)
  })

  it('选「+ 新建分组」后触发器显示该文案并出现名称输入框', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: '+ 新建分组' }))

    expect(screen.getByRole('combobox')).toHaveTextContent('+ 新建分组')
    expect(screen.getByLabelText('新分组名称')).toBeInTheDocument()
  })

  it('未选时显示占位符「请选择分组」', () => {
    setup()
    expect(screen.getByRole('combobox')).toHaveTextContent('请选择分组')
  })
})

describe('BatchAdjustGroupDialog 空 ids 守卫（INT-1780）', () => {
  it('ids 为空时「确定」禁用且不提交批量请求', async () => {
    const user = userEvent.setup()
    render(
      <BatchAdjustGroupDialog
        open
        onOpenChange={vi.fn()}
        count={0}
        ids={[]}
        groups={GROUPS}
      />
    )
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: '接线测试_分组A' }))

    const confirm = screen.getByRole('button', { name: '确定' })
    expect(confirm).toBeDisabled()
    await user.click(confirm)
    expect(batchTestcaseAction).not.toHaveBeenCalled()
  })
})
