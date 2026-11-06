/**
 * 组头操作面板测试（V9.7.10 TestCaseGroupActions 等价移植，11_用例域.md §3.5）：
 * 编辑/删除/新增用例/复制四钮 + 「批量修改」下拉九项；回收站态整组隐藏；
 * 批量动作按「有勾选用勾选，否则组内全量」resolveCaseIds。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CaseGroupActions, GROUP_BATCH_ITEMS } from '@/features/testcases/components/case-group-actions'

const setupUser = () => userEvent.setup()

describe('CaseGroupActions', () => {
  const baseProps = {
    name: '智能音箱功能测试',
    caseIds: ['tc-001', 'tc-002', 'tc-003'],
    selectedIds: [] as string[],
    trash: false,
  }

  it('渲染编辑/删除/新增用例/复制四钮与批量修改触发钮', () => {
    render(
      <CaseGroupActions
        {...baseProps}
        onEditGroup={vi.fn()}
        onDeleteGroup={vi.fn()}
        onCreateInGroup={vi.fn()}
        onCopyGroup={vi.fn()}
        onBatchAction={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: '编辑' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新增用例' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '复制' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /批量修改/ })).toBeInTheDocument()
  })

  it('批量修改下拉含九项（对齐 V9.7.10 逐字文案）', async () => {
    const user = setupUser()
    render(<CaseGroupActions {...baseProps} onBatchAction={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    expect(GROUP_BATCH_ITEMS).toHaveLength(9)
    expect(GROUP_BATCH_ITEMS.map((i) => i.label)).toEqual([
      '用例专属参数',
      '播放设备',
      '声压',
      '调整分组',
      '评价维度',
      '噪声',
      '标签生成名称',
      '管理标签',
      '用例参考更新',
    ])
    for (const item of GROUP_BATCH_ITEMS) {
      expect(await screen.findByText(item.label)).toBeInTheDocument()
    }
  })

  it('批量动作：无勾选用组内全量，有勾选用勾选集（resolveCaseIds 语义）', async () => {
    const user = setupUser()
    const onBatchAction = vi.fn()
    const { rerender } = render(
      <CaseGroupActions {...baseProps} onBatchAction={onBatchAction} />
    )
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('评价维度'))
    expect(onBatchAction).toHaveBeenCalledWith('dimensions', ['tc-001', 'tc-002', 'tc-003'])

    rerender(
      <CaseGroupActions
        {...baseProps}
        selectedIds={['tc-002']}
        onBatchAction={onBatchAction}
      />
    )
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('播放设备'))
    expect(onBatchAction).toHaveBeenCalledWith('device', ['tc-002'])
  })

  it('「删除用例」走 onBatchAction(delete) 真实批量通道（INT-1780：不再只 toast 假成功）', async () => {
    const user = setupUser()
    const onBatchAction = vi.fn()
    render(<CaseGroupActions {...baseProps} onBatchAction={onBatchAction} />)
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('删除用例'))
    expect(onBatchAction).toHaveBeenCalledWith('delete', ['tc-001', 'tc-002', 'tc-003'])
  })

  it('组内用例未加载（收起态）时传空 ids，由 openBatch 统一拦截提示（INT-1780）', async () => {
    const user = setupUser()
    const onBatchAction = vi.fn()
    render(
      <CaseGroupActions
        {...baseProps}
        caseIds={[]}
        selectedIds={[]}
        onBatchAction={onBatchAction}
      />
    )
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('调整分组'))
    expect(onBatchAction).toHaveBeenCalledWith('group', [])
  })

  it('INT-1970 返工 P2-2：已知组内全量（groupAllIds）→ 无勾选用整组，有勾选按 全量∩selected', async () => {
    const user = setupUser()
    const fullGroup = ['tc-001', 'tc-002', 'tc-003', 'tc-004', 'tc-005', 'tc-006']
    const onBatchAction = vi.fn()
    const { rerender } = render(
      <CaseGroupActions
        {...baseProps}
        groupAllIds={fullGroup}
        selected={new Set()}
        onBatchAction={onBatchAction}
      />
    )
    // 未勾选任何用例 → 批量范围 = 整组（不再只取已加载页）
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('评价维度'))
    expect(onBatchAction).toHaveBeenCalledWith('dimensions', fullGroup)

    // 已勾选 3 条（跨已加载/未加载）→ 批量范围 = 全量 ∩ selected，不再按已加载页截断
    onBatchAction.mockClear()
    rerender(
      <CaseGroupActions
        {...baseProps}
        groupAllIds={fullGroup}
        selected={new Set(['tc-002', 'tc-004', 'tc-006'])}
        onBatchAction={onBatchAction}
      />
    )
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('播放设备'))
    expect(onBatchAction).toHaveBeenCalledWith('device', ['tc-002', 'tc-004', 'tc-006'])
  })

  it('INT-1970 返工 P2-2：全量未知且有补取器 → 菜单项点击补取整组一次（含已勾选交集）', async () => {
    const user = setupUser()
    const fullGroup = ['tc-001', 'tc-002', 'tc-003', 'tc-004', 'tc-005', 'tc-006']
    const resolveGroupIds = vi.fn(async () => fullGroup)
    const onBatchAction = vi.fn()
    render(
      <CaseGroupActions
        {...baseProps}
        resolveGroupIds={resolveGroupIds}
        selected={new Set(['tc-001', 'tc-005'])}
        onBatchAction={onBatchAction}
      />
    )
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('噪声'))
    await waitFor(() => {
      expect(resolveGroupIds).toHaveBeenCalledTimes(1)
      expect(onBatchAction).toHaveBeenCalledWith('noise', ['tc-001', 'tc-005'])
    })
  })

  it('INT-1970 返工 P2-2：全量补取失败 → 回退已加载 ids，不阻塞批量动作', async () => {
    const user = setupUser()
    const resolveGroupIds = vi.fn(async () => {
      throw new Error('ids 查询失败')
    })
    const onBatchAction = vi.fn()
    render(
      <CaseGroupActions
        {...baseProps}
        resolveGroupIds={resolveGroupIds}
        selected={new Set(['tc-001'])}
        onBatchAction={onBatchAction}
      />
    )
    await user.click(screen.getByRole('button', { name: /批量修改/ }))
    await user.click(await screen.findByText('管理标签'))
    await waitFor(() => {
      expect(onBatchAction).toHaveBeenCalledWith('tags', ['tc-001', 'tc-002', 'tc-003'])
    })
  })

  it('回收站态整组操作面板隐藏（INT-215 口径）', () => {
    render(<CaseGroupActions {...baseProps} trash onBatchAction={vi.fn()} />)
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /批量修改/ })).not.toBeInTheDocument()
  })
})
