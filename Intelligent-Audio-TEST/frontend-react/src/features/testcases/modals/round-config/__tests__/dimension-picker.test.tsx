/**
 * 维度多选主/子分组云测试（照 V9.7.10 DimensionConfigPanel.buildCloudGroups + DimensionCloud
 * 主/子分组口径：主维度 chip「主」徽章 + 子维度数角标 + 勾选联动全部子维度；子维度 chip「子」徽章
 * + 树形分支符；搜索命中子维度带出父维度上下文、命中主维度时仅展示命中的子维度；父维度被算法
 * 过滤的子维度作孤儿子维度兜底）。
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

describe('DimensionPicker 主/子分组云（V9.7.10 口径）', () => {
  it('主维度分组渲染：主 chip 带「主」徽章 + 子维度数角标，子维度归属其下', () => {
    setup()
    // 主维度「识别准确率」+ 子维度数角标「2」
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    expect(screen.getAllByText('主').length).toBeGreaterThanOrEqual(2)
    // 子维度「字准率」「句准率」带「子」徽章
    expect(screen.getByText('字准率')).toBeInTheDocument()
    expect(screen.getByText('句准率')).toBeInTheDocument()
    expect(screen.getAllByText('子').length).toBeGreaterThanOrEqual(2)
    // 无子维度的主维度（唤醒成功率）仍平铺展示
    expect(screen.getByText('唤醒成功率')).toBeInTheDocument()
    expect(screen.getByText('对话连贯性')).toBeInTheDocument()
  })

  it('点击主维度 chip 联动全部子维度（含自身）', () => {
    const { onToggle } = setup()
    // 识别准确率（id 1）+ 子维度 11/12
    fireEvent.click(screen.getByRole('button', { name: /识别准确率/ }))
    expect(onToggle).toHaveBeenCalledWith([1, 11, 12], true)
  })

  it('已选主维度时点击 → 取消整组联动', () => {
    const { onToggle } = setup([1, 11, 12])
    fireEvent.click(screen.getByRole('button', { name: /识别准确率/ }))
    expect(onToggle).toHaveBeenCalledWith([1, 11, 12], false)
  })

  it('点击子维度 chip 只勾选自身', () => {
    const { onToggle } = setup()
    fireEvent.click(screen.getByRole('button', { name: /字准率/ }))
    expect(onToggle).toHaveBeenCalledWith([11], true)
    fireEvent.click(screen.getByRole('button', { name: /句准率/ }))
    expect(onToggle).toHaveBeenCalledWith([12], true)
  })

  it('搜索命中子维度带出父维度上下文（整组只展示命中的子维度）', () => {
    setup()
    typeSearch('字准率')
    expect(screen.getByText('字准率')).toBeInTheDocument()
    // 父维度「识别准确率」作为上下文展示
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    // 无关维度不渲染
    expect(screen.queryByText('语义理解')).not.toBeInTheDocument()
    expect(screen.queryByText('唤醒成功率')).not.toBeInTheDocument()
  })

  it('搜索命中主维度时仅展示命中的子维度（V9.7.10 kw 口径）', () => {
    setup()
    typeSearch('语义理解')
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    // 子维度「指令完成度」不命中关键词 → 不随组展示
    expect(screen.queryByText('指令完成度')).not.toBeInTheDocument()
    expect(screen.queryByText('识别准确率')).not.toBeInTheDocument()
  })

  it('清空搜索恢复全量分组渲染', () => {
    setup()
    typeSearch('字准率')
    expect(screen.getByText('字准率')).toBeInTheDocument()
    typeSearch('')
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    expect(screen.getByText('唤醒成功率')).toBeInTheDocument()
    expect(screen.getByText('对话连贯性')).toBeInTheDocument()
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

  it('已选 chip 高亮 + 计数 + aria-pressed', () => {
    setup([1])
    expect(screen.getByText('已选 1 项')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /识别准确率/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    expect(screen.getByRole('button', { name: /语义理解/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
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
