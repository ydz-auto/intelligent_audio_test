/**
 * 批量管理标签弹窗测试（11_用例域.md §5.3.7；INT-2102 分类分组 + INT-1295 口径保留）：
 * 已有标签点选区按分类分组（数据源 GET /tags/by-category；组头=分类名＋组内标签＋
 * 「未分类」尾组），排除已选 chips、空组头隐藏；改名模式 Select 不受影响
 * （INT-1591：新旧同名禁用确定，不发请求）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TagCategoryGroup, TagItem } from '@/domain/models/testTag'
import { BatchManageTagsDialog } from '@/features/testcases/modals/batch-manage-tags-dialog'
import { batchTestcaseAction } from '@/infrastructure/api/testcases-batch-api'
import { fetchTagsByCategory } from '@/infrastructure/api/tags-api'

vi.mock('@/infrastructure/api/testcases-batch-api', () => ({
  batchTestcaseAction: vi.fn(),
}))

vi.mock('@/infrastructure/api/tags-api', () => ({
  fetchTagsByCategory: vi.fn(),
}))

const mockedBatch = vi.mocked(batchTestcaseAction)
const mockedByCategory = vi.mocked(fetchTagsByCategory)

const tag = (id: number, name: string, categoryId: number | null, categoryName: string | null): TagItem => ({
  id,
  name,
  description: null,
  color: categoryId ? '#10b981' : null,
  categoryId,
  categoryName,
  createdAt: null,
  updatedAt: null,
})

/** 分类分组夹具：识别类 2 个 + 未分类 1 个（未分类尾组，category:null） */
const mockGroups: TagCategoryGroup[] = [
  {
    category: {
      id: 1,
      name: '识别类',
      description: null,
      color: '#10b981',
      sortOrder: 1,
      tagCount: 2,
      createdAt: null,
      updatedAt: null,
    },
    tags: [tag(1, '标签1', 1, '识别类'), tag(2, '标签2', 1, '识别类')],
  },
  {
    category: null,
    tags: [tag(3, '标签3', null, null)],
  },
]

const mockTags: TagItem[] = mockGroups.flatMap((g) => g.tags)

const setup = (groups: TagCategoryGroup[] = mockGroups) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  mockedByCategory.mockResolvedValue(groups)
  return render(
    <QueryClientProvider client={client}>
      <BatchManageTagsDialog
        open
        onOpenChange={vi.fn()}
        count={3}
        ids={['tc-1', 'tc-2', 'tc-3']}
        tags={mockTags}
      />
    </QueryClientProvider>
  )
}

describe('BatchManageTagsDialog（§5.3.7，INT-2102 分类分组）', () => {
  beforeEach(() => {
    mockedBatch.mockReset()
    mockedBatch.mockResolvedValue({ updatedCount: 3 })
    mockedByCategory.mockReset()
  })

  it('已有标签点选区按分类分组：组头=分类名 + 组内标签 + 「未分类」尾组', async () => {
    setup()

    expect(await screen.findByText('已有标签（点击添加）：')).toBeInTheDocument()
    expect(await screen.findByText('识别类')).toBeInTheDocument()
    expect(screen.getByText('未分类')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签3' })).toBeInTheDocument()
    // 不再平铺分页（无页码指示）
    expect(screen.queryByText(/^\d+ \/ \d+$/)).not.toBeInTheDocument()
  })

  it('已选 chips 从候选剔除：点选已有标签 → 成为已选 Badge 且从候选消失；组内全选后组头隐藏', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(await screen.findByRole('button', { name: '标签1' }))
    // 已选 Badge「标签1」出现（可移除）
    expect(screen.getByRole('button', { name: '移除 标签1' })).toBeInTheDocument()
    // 候选区不再显示已选标签，组内其余标签与组头仍在
    expect(screen.queryByRole('button', { name: '标签1' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签2' })).toBeInTheDocument()
    expect(screen.getByText('识别类')).toBeInTheDocument()

    // 识别类组内全部点选 → 空组头隐藏，未分类组仍在
    await user.click(screen.getByRole('button', { name: '标签2' }))
    expect(screen.queryByText('识别类')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '标签3' })).toBeInTheDocument()
    expect(screen.getByText('未分类')).toBeInTheDocument()
  })

  it('移除模式：提示文案「已有标签（点击移除）：」，分组展示不变', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(screen.getByText('移除标签'))
    expect(screen.getByText('已有标签（点击移除）：')).toBeInTheDocument()
    expect(await screen.findByText('识别类')).toBeInTheDocument()
    expect(screen.getByText('未分类')).toBeInTheDocument()
  })

  it('提交 add_tags 按选中用例 ids 携带已选 chips', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(await screen.findByRole('button', { name: '标签1' }))
    await user.click(screen.getByRole('button', { name: '标签3' }))
    await user.click(screen.getByRole('button', { name: '确定' }))

    expect(mockedBatch).toHaveBeenCalledWith(
      'add_tags',
      ['tc-1', 'tc-2', 'tc-3'],
      { tags: ['标签1', '标签3'] }
    )
  })

  describe('改名模式（INT-1591：新旧同名禁用确定）', () => {
    const chooseRenameSource = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByText('修改标签名字'))
      await user.click(screen.getByRole('combobox'))
      const option = await screen.findByRole('option', { name: '标签1' })
      await user.click(option)
    }

    it('新标签名与原标签名相同 →「确定」禁用且不发请求', async () => {
      const user = userEvent.setup()
      setup()
      await chooseRenameSource(user)

      await user.type(screen.getByPlaceholderText('输入新标签名称'), '标签1')

      const confirm = screen.getByRole('button', { name: '确定' })
      expect(confirm).toBeDisabled()
      await user.click(confirm)
      expect(mockedBatch).not.toHaveBeenCalled()
    })

    it('新标签名不同 →「确定」可用并提交 rename_tag', async () => {
      const user = userEvent.setup()
      setup()
      await chooseRenameSource(user)

      await user.type(screen.getByPlaceholderText('输入新标签名称'), '标签1改')
      await user.click(screen.getByRole('button', { name: '确定' }))

      expect(mockedBatch).toHaveBeenCalledWith('rename_tag', [], {
        oldTagName: '标签1',
        newTagName: '标签1改',
      })
    })
  })
})
