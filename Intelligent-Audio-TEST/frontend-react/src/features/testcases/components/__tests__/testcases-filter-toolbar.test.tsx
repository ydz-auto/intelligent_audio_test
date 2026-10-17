/**
 * 用例筛选工具栏测试（11_用例域.md §3.4/§3.6）：
 * 搜索防抖 + facet + 收藏/回收站 + 重置；标签 facet 单选按分类分组
 * （INT-592 由多选改单选）+ Command 搜索 + 客户端聚合计数；选中态后
 * 工具栏右端「标签操作」下拉（收编①：编辑/删除/复制标签下用例，§3.6）。
 */
import { render, screen, within } from '@testing-library/react'
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
  MOCK_TEST_CASES.filter((c) => !c.deleted && c.tags.includes(name)).length

function renderToolbar(filters: Record<string, unknown> = {}, tags = MOCK_TAGS) {
  const props = {
    filters: filters as never,
    onChange: vi.fn(),
    onReset: vi.fn(),
    isFiltered: false,
    groups: GROUPS,
    tags,
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

  it('标签 facet 选项按分类分组展示（§3.4 组头=分类名）且带聚合计数', async () => {
    const user = setupUser()
    renderToolbar()
    await user.click(screen.getByRole('button', { name: '标签全部' }))
    // 组头=分类名（INT-487：GET /tags/by-category）
    expect(screen.getByText('人数')).toBeInTheDocument()
    expect(screen.getByText('场景')).toBeInTheDocument()
    expect(screen.getByText('设备类型')).toBeInTheDocument()
    // 选项计数从已加载集聚合（§3.4 客户端聚合口径）
    const speakerOption = screen.getByRole('button', { name: '音箱' })
    expect(within(speakerOption).getByText(String(tagCount('音箱')))).toBeInTheDocument()
  })

  it('标签 facet 单选：选中单个标签 → onChange({ tag })', async () => {
    const user = setupUser()
    const props = renderToolbar()
    await user.click(screen.getByRole('button', { name: '标签全部' }))
    await user.click(screen.getByRole('button', { name: '音箱' }))
    expect(props.onChange).toHaveBeenCalledWith(expect.objectContaining({ tag: '音箱' }))
  })

  it('标签 facet 单选：选中标签再点 = 取消（清空标签筛选）', async () => {
    const user = setupUser()
    const props = renderToolbar({ tag: '音箱' })
    await user.click(screen.getByRole('button', { name: '标签音箱' }))
    await user.click(screen.getByRole('button', { name: '音箱' }))
    expect(props.onChange).toHaveBeenCalledWith(expect.objectContaining({ tag: null }))
  })

  it('标签 facet Command 搜索过滤选项（§3.4）', async () => {
    const user = setupUser()
    renderToolbar()
    await user.click(screen.getByRole('button', { name: '标签全部' }))
    await user.type(screen.getByRole('textbox', { name: '搜索标签' }), '音箱')
    expect(screen.getByRole('button', { name: '音箱' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '1人' })).not.toBeInTheDocument()
  })

  it('标签 facet 数据源为空时显示「暂无标签」（§3.4 空态）', async () => {
    const user = setupUser()
    renderToolbar({}, [])
    await user.click(screen.getByRole('button', { name: '标签全部' }))
    expect(screen.getByText('暂无标签')).toBeInTheDocument()
  })

  it('§3.6 收编①：标签 facet 选中态后工具栏右端出现「标签操作」下拉', () => {
    renderToolbar({ tag: '音箱' })
    expect(screen.getByRole('button', { name: /标签操作/ })).toBeInTheDocument()
  })

  it('删除标签 → 级联删除确认（§3.6 destructive 文案逐字 + 计数），确认后关闭', async () => {
    const user = setupUser()
    renderToolbar({ tag: '音箱' })
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
    renderToolbar({ tag: '音箱' })
    await user.click(screen.getByRole('button', { name: /标签操作/ }))
    await user.click(await screen.findByText('复制标签下用例'))
    expect(screen.getByText(/复制后将生成新标签：音箱_copy/)).toBeInTheDocument()
    expect(screen.getByText('同时复制到新分组')).toBeInTheDocument()
  })

  it('P2-1 回归：权限态变化时无 hook 早退——只读角色「标签操作」整组保留、逐钮禁用（§7 注 1）', async () => {
    const user = setupUser()
    const props = {
      filters: { tag: '音箱' } as never,
      onChange: vi.fn(),
      onReset: vi.fn(),
      isFiltered: false,
      groups: GROUPS,
      tags: MOCK_TAGS,
      dimensions: DIMENSIONS,
      onRestoreAll: vi.fn(),
    }
    const { rerender } = render(<TestCasesFilterToolbar {...props} />)
    // 写权限用户（MOCK_USER '*'）：下拉出现
    expect(screen.getByRole('button', { name: /标签操作/ })).toBeInTheDocument()

    // 权限态变化（登出/角色切换 → 写权限全失）：挂载不崩（P2-1 早退跳过 hook 会抛
    // 「Rendered fewer hooks」）；§7 注 1 整组保留、写钮逐钮置灰 + Tooltip
    useAuthStore.setState({
      user: {
        id: 'readonly-user-001',
        username: 'algo_engineer',
        displayName: '算法工程师',
        roleName: '算法工程师',
        permissions: ['testcase:read'],
      },
    })
    rerender(<TestCasesFilterToolbar {...props} />)
    expect(screen.getByRole('button', { name: /标签操作/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /标签操作/ }))
    // 写钮逐钮 aria-disabled + Tooltip（§7 注 1 口径；jest-dom toBeDisabled 不认 aria-disabled）
    expect(screen.getByRole('menuitem', { name: '编辑标签' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: '删除标签' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: '复制标签下用例' })).toHaveAttribute('aria-disabled', 'true')
  })
})
