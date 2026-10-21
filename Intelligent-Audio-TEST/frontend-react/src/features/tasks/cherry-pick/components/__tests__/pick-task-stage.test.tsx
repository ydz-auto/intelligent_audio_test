/**
 * 挑选阶段 1 任务选择组件测试（18_挑选合并交互重设计.md §3.8.2，INT-1047）。
 * 两阶段状态机阶段 1：搜索/多选/全选当前筛选/清空/下一步（选中 ≥1 启用）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  PickTaskStage,
  type PickTaskRow,
} from '@/features/tasks/cherry-pick/components/pick-task-stage'

const TASKS: PickTaskRow[] = [
  { taskId: 1042, taskName: '任务A', executionStatus: 'completed', createdAt: '2026-10-18 09:00', count: 36 },
  { taskId: 1041, taskName: '任务B', executionStatus: 'failed', createdAt: '2026-10-18 10:00', count: 24 },
  { taskId: 1040, taskName: '任务C', executionStatus: 'stopped', createdAt: '2026-10-17 15:00', count: 12 },
]

function setup(selected = new Set<number>(), overrides: Partial<Parameters<typeof PickTaskStage>[0]> = {}) {
  const onToggle = vi.fn()
  const onSelectAll = vi.fn()
  const onClear = vi.fn()
  const onNext = vi.fn()
  const onRetry = vi.fn()
  render(
    <PickTaskStage
      tasks={TASKS}
      selectedTaskIds={selected}
      loading={false}
      isError={false}
      onRetry={onRetry}
      onToggle={onToggle}
      onSelectAll={onSelectAll}
      onClear={onClear}
      onNext={onNext}
      {...overrides}
    />
  )
  return { onToggle, onSelectAll, onClear, onNext, onRetry }
}

describe('PickTaskStage（§3.8.2 阶段 1 选择任务）', () => {
  it('渲染任务行：名称 + 执行状态 + 结果计数 + 创建时间', () => {
    setup()
    expect(screen.getByText('任务A')).toBeInTheDocument()
    expect(screen.getByText('任务B')).toBeInTheDocument()
    expect(screen.getByText('任务C')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('执行失败')).toBeInTheDocument()
    expect(screen.getByText('已停止')).toBeInTheDocument()
    expect(screen.getByText('36 条')).toBeInTheDocument()
    expect(screen.getByText('2026-10-18 09:00')).toBeInTheDocument()
  })

  it('勾选任务触发 onToggle，已选计数更新', () => {
    const { onToggle } = setup(new Set([1042]))
    expect(screen.getByText('1', { selector: '.font-medium' })).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('选择任务 任务A'))
    expect(onToggle).toHaveBeenCalledWith(1042)
    fireEvent.click(screen.getByLabelText('选择任务 任务B'))
    expect(onToggle).toHaveBeenCalledWith(1041)
  })

  it('搜索过滤任务列表（按名称），全选当前筛选传命中集', () => {
    const { onSelectAll } = setup()
    const input = screen.getByLabelText('搜索任务名称')
    fireEvent.change(input, { target: { value: '任务B' } })
    expect(screen.getByText('任务B')).toBeInTheDocument()
    expect(screen.queryByText('任务A')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('全选当前筛选'))
    expect(onSelectAll).toHaveBeenCalledWith([1041])
  })

  it('全选当前筛选（无搜索）传全部任务', () => {
    const { onSelectAll } = setup()
    fireEvent.click(screen.getByText('全选当前筛选'))
    expect(onSelectAll).toHaveBeenCalledWith([1042, 1041, 1040])
  })

  it('清空触发 onClear；下一步：选择结果（{n}）按选中数启用/禁用', () => {
    const { onClear, onNext } = setup(new Set([1042]))
    const nextBtn = screen.getByRole('button', { name: '下一步：选择结果（1）' })
    expect(nextBtn).toBeEnabled()
    fireEvent.click(nextBtn)
    expect(onNext).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByText('清空'))
    expect(onClear).toHaveBeenCalledTimes(1)
  })

  it('无选中时「下一步」禁用', () => {
    setup()
    const nextBtn = screen.getByRole('button', { name: '下一步：选择结果（0）' })
    expect(nextBtn).toBeDisabled()
  })

  it('空态：暂无可挑选的终态任务', () => {
    setup(new Set(), { tasks: [] })
    expect(screen.getByText('暂无可挑选的终态任务')).toBeInTheDocument()
  })
})
