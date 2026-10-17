/**
 * 用例筛选工具栏测试（11_用例域.md §3.4/§3.6）：
 * 搜索防抖 + facet + 收藏/回收站 + 重置；标签 facet 选中态后工具栏右端
 * 「标签操作」下拉（收编①：编辑/删除/复制标签下用例/按标签批量修改，§3.6）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import { MOCK_TAGS, MOCK_TEST_CASES } from '@/infrastructure/mock/testcases-mock'
import { MOCK_USER, useAuthStore } from '@/infrastructure/stores/auth-store'
import { TestCasesFilterToolbar } from '@/features/testcases/components/testcases-filter-toolbar'

const GROUPS: TestCaseGroup[] = [
  {
    id: 'g1',
    name: '智能音箱功能测试',
    description: null,
    algorithmType: 'asr-v3',
    createdAt: '2026-09-01 11:00',
    updatedAt: '2026-10-14 16:20',
    testCaseCount: 5,
  },
]

const DIMENSIONS: EvaluationDimensionItem[] = [
  {
    id: 1,
    name: '识别准确率',
    description: null,
    dimensionType: 'main',
    parentDimensionId: null,
    categoryId: null,
    weight: 9,
    status: true,
    createdAt: '2026-08-01 09:00',
    updatedAt: '2026-09-20 11:00',
  },
]

const tagCount = (name: string) =>
  MOCK_TEST_CASES.filter((c) => c.tags.includes(name)).length

function renderToolbar(filters: Record<string, unknown> = {}) {
  const props = {
    filters: filters as never,
    onChange: vi.fn(),
    onReset: vi.fn(),
    isFiltered: false,
    groups: GROUPS,
    tags: MOCK_TAGS,
    dimensions: DIMENSIONS,
    onRestoreAll: vi.fn(),
  }
  render(<TestCasesFilterToolbar {...props} />)
  return props
}

const setupUser = () => userEvent.setup()

describe('TestCasesFilterToolbar', () => {
  beforeEach(() => {
    // 默认登录态：演示管理员（permissions '*'），标签操作入口依赖写权限判定
    useAuthStore.setState({ user: MOCK_USER })
  })

  it('无标签筛选时不出现「标签操作」入口', () => {
    renderToolbar()
    expect(screen.queryByRole('button', { name: /标签操作/ })).not.toBeInTheDocument()
  })

  it('§3.6 收编①：标签 facet 选中态后工具栏右端出现「标签操作」下拉', () => {
    renderToolbar({ tags: ['音箱'] })
    expect(screen.getByRole('button', { name: /标签操作/ })).toBeInTheDocument()
  })

  it('删除标签 → 级联删除确认（§3.6 destructive 文案逐字 + 计数），确认后关闭', async () => {
    const user = setupUser()
    renderToolbar({ tags: ['音箱'] })
    await user.click(screen.getByRole('button', { name: /标签操作/ }))
    await user.click(await screen.findByText('删除标签'))
    expect(
      screen.getByText(
        `确定要删除标签「音箱」吗？该操作将级联删除标签下的 ${tagCount('音箱')} 个用例，不可恢复！`
      )
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '删除' }))
    expect(screen.queryByText(/确定要删除标签/)).not.toBeInTheDocument()
  })

  it('复制标签下用例 → 确认含「同时复制到新分组」Checkbox', async () => {
    const user = setupUser()
    renderToolbar({ tags: ['音箱'] })
    await user.click(screen.getByRole('button', { name: /标签操作/ }))
    await user.click(await screen.findByText('复制标签下用例'))
    expect(screen.getByText(/复制后将生成新标签：音箱_copy/)).toBeInTheDocument()
    expect(screen.getByText('同时复制到新分组')).toBeInTheDocument()
  })

  it('多标签选中时编辑/删除禁用（Tooltip「请先单选一个标签」）', async () => {
    const user = setupUser()
    renderToolbar({ tags: ['音箱', '中文'] })
    await user.click(screen.getByRole('button', { name: /标签操作/ }))
    const editItem = await screen.findByText('编辑标签')
    expect(editItem).toHaveAttribute('data-disabled')
    expect(editItem).toHaveAttribute('title', '请先单选一个标签')
  })
})
