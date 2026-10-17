/**
 * 维度多选平铺 chips 云测试（照 V9.7.10 DimensionConfigPanel/RoundEvaluationEditor
 * 平铺口径：搜索「搜索评估维度」+ 已选计数 + 平铺 chip 独立勾选，无主/子联动分组）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MOCK_CASE_DIMENSIONS } from '@/infrastructure/mock/testcases-mock'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'

const setup = (selected: number[] = []) => {
  const onToggle = vi.fn()
  render(
    <DimensionPicker
      dimensions={MOCK_CASE_DIMENSIONS}
      selected={selected}
      onToggle={onToggle}
    />
  )
  return { onToggle }
}

const typeSearch = (text: string) => {
  fireEvent.change(screen.getByPlaceholderText('搜索评估维度'), {
    target: { value: text },
  })
}

describe('DimensionPicker 平铺 chips 云（V9.7.10 口径）', () => {
  it('全量平铺渲染主/子维度 chip，无层级折叠', () => {
    setup()
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    expect(screen.getByText('字准率')).toBeInTheDocument()
    expect(screen.getByText('句准率')).toBeInTheDocument()
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    expect(screen.getByText('指令完成度')).toBeInTheDocument()
  })

  it('搜索按名称/描述/keywords 命中单个维度 chip', () => {
    setup()
    typeSearch('字准率')
    expect(screen.getByText('字准率')).toBeInTheDocument()
    // 平铺搜索不做「带出父维度整组」——无关维度不渲染
    expect(screen.queryByText('识别准确率')).not.toBeInTheDocument()
    expect(screen.queryByText('句准率')).not.toBeInTheDocument()
  })

  it('搜索命中主维度「语义理解」只带自身 chip，不带子维度「指令完成度」', () => {
    setup()
    typeSearch('语义理解')
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    expect(screen.queryByText('指令完成度')).not.toBeInTheDocument()
    expect(screen.queryByText('识别准确率')).not.toBeInTheDocument()
  })

  it('清空搜索恢复全量渲染', () => {
    setup()
    typeSearch('字准率')
    expect(screen.getByText('字准率')).toBeInTheDocument()
    typeSearch('')
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    expect(screen.getByText('唤醒成功率')).toBeInTheDocument()
  })

  it('搜索无命中显示「没有匹配的评估维度」空态', () => {
    setup()
    typeSearch('完全不存在的关键词')
    expect(screen.getByText('没有匹配的评估维度')).toBeInTheDocument()
    expect(screen.queryByText('识别准确率')).not.toBeInTheDocument()
  })

  it('空态三态：无维度数据时「暂无可用维度」', () => {
    render(
      <DimensionPicker dimensions={[]} selected={[]} onToggle={vi.fn()} />
    )
    expect(screen.getByText('暂无可用维度')).toBeInTheDocument()
  })

  it('已选 chip 高亮 + 计数 + aria-pressed，点击单维度触发 onToggle([id])', () => {
    const { onToggle } = setup([1])
    // 已选计数
    expect(screen.getByText('已选 1 项')).toBeInTheDocument()
    // 已选 chip aria-pressed=true，未选 chip aria-pressed=false
    const selectedChip = screen.getByRole('button', { name: /识别准确率/ })
    expect(selectedChip).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /语义理解/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
    // 点击未选 chip → onToggle([id], true)
    fireEvent.click(screen.getByRole('button', { name: /语义理解/ }))
    expect(onToggle).toHaveBeenCalledWith([2], true)
    // 点击已选 chip → onToggle([id], false)
    fireEvent.click(selectedChip)
    expect(onToggle).toHaveBeenCalledWith([1], false)
  })

  it('按当前算法过滤可用维度（associated_algorithms 口径）', () => {
    render(
      <DimensionPicker
        dimensions={MOCK_CASE_DIMENSIONS}
        algorithmType='eval-ensemble'
        selected={[]}
        onToggle={vi.fn()}
      />
    )
    // eval-ensemble 关联：语义理解/对话连贯性（子维度指令完成度无关联 → 不渲染）
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    expect(screen.getByText('对话连贯性')).toBeInTheDocument()
    expect(screen.queryByText('识别准确率')).not.toBeInTheDocument()
    expect(screen.queryByText('字准率')).not.toBeInTheDocument()
  })
})
