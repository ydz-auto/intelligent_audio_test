/**
 * 用例筛选工具栏·分组 facet 错误态测试（INT-2331，与 INT-1560 标签 facet 同型）。
 * 背景：GET /groups 失败时分组下拉只剩「未分组」兜底项，页面无任何错误提示，
 * 用户无法区分「确实没有分组」与「分组接口挂了」。
 * 口径：失败时触发器显示「加载失败」并在下拉内给出「分组加载失败」+ 重试。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import {
  TestCasesFilterToolbar,
  type TestCasesFilterToolbarProps,
} from '@/features/testcases/components/testcases-filter-toolbar'

function baseProps(
  overrides: Partial<TestCasesFilterToolbarProps> = {}
): TestCasesFilterToolbarProps {
  return {
    filters: {},
    onChange: vi.fn(),
    onReset: vi.fn(),
    isFiltered: false,
    groups: [],
    tags: [],
    dimensions: [],
    categories: [],
    tagCategories: [],
    onUpdateTag: vi.fn(),
    onDeleteTag: vi.fn(),
    onCopyTag: vi.fn(),
    cases: [],
    onRestoreAll: vi.fn(),
    ...overrides,
  }
}

describe('用例筛选工具栏·分组 facet 错误态（INT-2331）', () => {
  it('分组查询失败：触发器显示「分组 / 加载失败」，下拉给出错误与重试', async () => {
    const onRetryGroups = vi.fn()
    render(
      <TestCasesFilterToolbar
        {...baseProps({ groupsError: true, onRetryGroups })}
      />
    )

    const trigger = screen.getByRole('button', { name: /分组.*加载失败/ })
    expect(trigger).toBeInTheDocument()

    await userEvent.click(trigger)
    expect(screen.getByText('分组加载失败')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetryGroups).toHaveBeenCalledTimes(1)
  })

  it('分组查询正常：触发器显示「全部」，不出现错误文案', () => {
    render(<TestCasesFilterToolbar {...baseProps()} />)

    expect(screen.getByRole('button', { name: /分组.*全部/ })).toBeInTheDocument()
    expect(screen.queryByText('加载失败')).not.toBeInTheDocument()
  })
})
