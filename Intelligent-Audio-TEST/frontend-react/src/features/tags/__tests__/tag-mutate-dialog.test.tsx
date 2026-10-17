/**
 * 标签表单弹窗测试（11_用例域.md §5.4 + INT-504 标签分类体系）：
 * P1 修复——未选分类时 Select 触发钮显示占位「请选择所属分类」（不显示字面量 none）；
 * P2 修复——选中「距离」后触发钮显示分类名「距离」（不显示分类 id 6）；
 * 必选分类口径——未选分类时「创建」禁用，选分类+填名后可用。
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { MOCK_TAG_CATEGORIES } from '@/infrastructure/mock/testcases-mock'
import { TagEditDialog } from '@/features/tags/tag-mutate-dialog'

function Harness() {
  return (
    <TagEditDialog
      open
      onOpenChange={() => undefined}
      tag={null}
      categories={MOCK_TAG_CATEGORIES}
      presetCategoryId={null}
    />
  )
}

function getTrigger() {
  // Base UI Select 触发钮：aria-haspopup=listbox
  return screen.getByRole('combobox')
}

describe('TagEditDialog 所属分类（INT-504）', () => {
  it('P1：未选分类时触发钮显示占位「请选择所属分类」，不显示 none', () => {
    render(<Harness />)
    const trigger = getTrigger()
    expect(trigger).toHaveTextContent('请选择所属分类')
    expect(trigger).not.toHaveTextContent('none')
  })

  it('P2：选中「距离」后触发钮显示分类名而非分类 id', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const trigger = getTrigger()
    await user.click(trigger)
    // 下拉选项含「距离」（含分类 id 6 的项，选它后应显示名称）
    const distanceItem = await screen.findByText('距离')
    expect(distanceItem).toBeInTheDocument()
    await user.click(distanceItem)
    expect(trigger).toHaveTextContent('距离')
    expect(trigger).not.toHaveTextContent('6')
  })

  it('必选分类：未选分类「创建」禁用；选分类 + 填名后可用', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const dialog = screen.getByRole('dialog')
    const createBtn = within(dialog).getByRole('button', { name: '创建' })
    expect(createBtn).toBeDisabled()
    // 填名但不选分类 → 仍禁用
    await user.type(screen.getByLabelText(/标签名称/), '距离测试标签')
    expect(createBtn).toBeDisabled()
    // 选分类「距离」→ 可用
    await user.click(getTrigger())
    await user.click(await screen.findByText('距离'))
    expect(createBtn).toBeEnabled()
  })
})
