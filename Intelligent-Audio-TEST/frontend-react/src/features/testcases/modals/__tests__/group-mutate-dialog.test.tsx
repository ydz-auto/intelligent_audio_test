/**
 * 新建/编辑分组弹窗（11_用例域.md §5.7.4 + INT-1658）。
 * 页面级「新建分组」以 group=null 打开 → 标题「新建分组」、提交走 POST /groups；
 * 对话框常挂载，连续打开（group 恒 null）须清空上次未提交输入，不得残留。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestCaseGroup } from '@/domain/models/testCaseGroup'

const mocks = vi.hoisted(() => ({
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
}))

vi.mock('@/infrastructure/api/groups-api', () => ({
  createGroup: mocks.createGroup,
  updateGroup: mocks.updateGroup,
}))

// 算法选项走 shell query（需 QueryClient 上下文），本弹窗测试只关心分组表单，整钩子打桩
vi.mock('@/application/hooks/use-algorithm-options', () => ({
  useAlgorithmOptions: () => ({
    options: [{ value: 'asr-v3', name: 'ASR V3' }],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    canRead: true,
  }),
}))

import { GroupMutateDialog } from '@/features/testcases/modals/group-mutate-dialog'

const EXISTING_GROUP: TestCaseGroup = {
  id: '7',
  name: '回归组',
  description: '既有描述',
  algorithmType: 'asr-v3',
  createdAt: '',
  updatedAt: '',
  testCaseCount: 2,
}

describe('GroupMutateDialog（INT-1658 页面级建组入口）', () => {
  beforeEach(() => {
    mocks.createGroup.mockReset().mockResolvedValue({ id: '9' })
    mocks.updateGroup.mockReset().mockResolvedValue(undefined)
  })

  it('group=null → 标题「新建分组」，提交走 POST /groups', async () => {
    const user = userEvent.setup()
    render(<GroupMutateDialog open onOpenChange={vi.fn()} group={null} />)

    expect(screen.getByText('新建分组')).toBeInTheDocument()
    const nameInput = screen.getByLabelText('分组名称 *')
    expect(nameInput).toHaveValue('')

    await user.type(nameInput, '接线测试_页面建组')
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(mocks.createGroup).toHaveBeenCalledWith({
      name: '接线测试_页面建组',
      description: null,
      algorithmType: null,
    })
    expect(mocks.updateGroup).not.toHaveBeenCalled()
  })

  it('连续以 group=null 打开：清空上次未提交输入（不残留）', async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <GroupMutateDialog open onOpenChange={vi.fn()} group={null} />
    )
    await user.type(screen.getByLabelText('分组名称 *'), '残留输入')

    // 关闭 → 重开（group 仍为 null，仅 open 变化）
    rerender(<GroupMutateDialog open={false} onOpenChange={vi.fn()} group={null} />)
    rerender(<GroupMutateDialog open onOpenChange={vi.fn()} group={null} />)

    expect(screen.getByLabelText('分组名称 *')).toHaveValue('')
  })

  it('group=null 创建成功 → onCreated 收到新建分组 id（facet 底部入口据此预填筛选）', async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    const onOpenChange = vi.fn()
    render(
      <GroupMutateDialog
        open
        onOpenChange={onOpenChange}
        group={null}
        onCreated={onCreated}
      />
    )

    await user.type(screen.getByLabelText('分组名称 *'), '接线测试_预填筛选')
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(onCreated).toHaveBeenCalledWith({ id: '9', name: '接线测试_预填筛选' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('group 非空（编辑）不触发 onCreated', async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    render(
      <GroupMutateDialog
        open
        onOpenChange={vi.fn()}
        group={EXISTING_GROUP}
        onCreated={onCreated}
      />
    )

    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(onCreated).not.toHaveBeenCalled()
  })

  it('group 非空 → 标题「编辑分组」，提交走 PUT /groups/{id}', async () => {
    const user = userEvent.setup()
    render(<GroupMutateDialog open onOpenChange={vi.fn()} group={EXISTING_GROUP} />)

    expect(screen.getByText('编辑分组')).toBeInTheDocument()
    expect(screen.getByLabelText('分组名称 *')).toHaveValue('回归组')

    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(mocks.updateGroup).toHaveBeenCalledWith('7', {
      name: '回归组',
      description: '既有描述',
      algorithmType: 'asr-v3',
    })
    expect(mocks.createGroup).not.toHaveBeenCalled()
  })
})
