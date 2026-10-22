/**
 * 批量管理标签弹窗测试（11_用例域.md §5.3.7；INT-1295）：
 * 已有标签点选区照现 Vue availableSuggestions（排除已选 chips）+ 分页 20 条/页：
 * 首屏 20 条、分页 上一页/下一页、已选 chips 从候选剔除、提交载荷（add_tags 按 ids）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TagItem } from '@/domain/models/testTag'
import { BatchManageTagsDialog } from '@/features/testcases/modals/batch-manage-tags-dialog'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

const mockedBatch = vi.mocked(batchTestcaseAction)

/** 25 个标签：分页验证（20/页 → 2 页） */
const mockTags: TagItem[] = Array.from({ length: 25 }, (_, i) => ({
  id: i + 1,
  name: `标签${i + 1}`,
  description: null,
  color: '#10b981',
  categoryId: null,
  categoryName: null,
  createdAt: null,
  updatedAt: null,
}))

const setup = (tags: TagItem[] = mockTags) => {
  render(
    <BatchManageTagsDialog
      open
      onOpenChange={vi.fn()}
      count={3}
      ids={['tc-1', 'tc-2', 'tc-3']}
      tags={tags}
    />
  )
}

describe('BatchManageTagsDialog（§5.3.7，INT-1295 分页）', () => {
  beforeEach(() => {
    mockedBatch.mockReset()
    mockedBatch.mockResolvedValue({ updatedCount: 3 })
  })

  it('已有标签点选区：首屏 20 条 + 分页「1 / 2」，下一页翻到剩余 5 条', async () => {
    const user = userEvent.setup()
    setup()

    expect(screen.getByText('已有标签（点击添加）：')).toBeInTheDocument()
    // 首屏 20 条：第 1 条可见、第 21 条不可见
    expect(screen.getByRole('button', { name: '标签1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '标签21' })).not.toBeInTheDocument()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '下一页' }))
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签21' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签25' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '上一页' }))
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '标签21' })).not.toBeInTheDocument()
  })

  it('已选 chips 从候选剔除：点选已有标签 → 成为已选 Badge 且从候选消失', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByRole('button', { name: '标签1' }))
    // 已选 Badge「标签1」出现（可移除）
    expect(screen.getByRole('button', { name: '移除 标签1' })).toBeInTheDocument()
    // 候选区不再显示已选标签
    expect(screen.queryByRole('button', { name: '标签1' })).not.toBeInTheDocument()
    // 其余候选仍在
    expect(screen.getByRole('button', { name: '标签2' })).toBeInTheDocument()
  })

  it('移除模式：提示文案「已有标签（点击移除）：」，且与添加模式共用分页', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByText('移除标签'))
    expect(screen.getByText('已有标签（点击移除）：')).toBeInTheDocument()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
  })

  it('提交 add_tags 按选中用例 ids 携带已选 chips', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByRole('button', { name: '标签1' }))
    await user.click(screen.getByRole('button', { name: '标签2' }))
    await user.click(screen.getByRole('button', { name: '确定' }))

    expect(mockedBatch).toHaveBeenCalledWith(
      'add_tags',
      ['tc-1', 'tc-2', 'tc-3'],
      { tags: ['标签1', '标签2'] }
    )
  })
})
