/**
 * 维度多选搜索交互测试（11_用例域.md §5.1.2：搜索命中主维度带出整组、
 * 命中子维度带出父维度并自动展开；审计 P2-1 回归）。
 * 空态三态中「没有匹配的评估维度」以渲染主维度集为准（P2-1：子维度命中
 * 但无主维度渲染时不再空白）。
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

describe('DimensionPicker 搜索交互（§5.1.2）', () => {
  it('搜索命中主维度「语义理解」带出整组并自动展开（子维度「指令完成度」可见）', () => {
    setup()
    typeSearch('语义理解')
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    // 整组子维度随主维度带出并自动展开
    expect(screen.getByText('指令完成度')).toBeInTheDocument()
    // 不相关维度不渲染
    expect(screen.queryByText('识别准确率')).not.toBeInTheDocument()
  })

  it('搜索命中子维度「字准率」带出父维度「识别准确率」并自动展开整组', () => {
    setup()
    typeSearch('字准率')
    // 父维度被带出
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    // 整组子维度可见（命中项「字准率」+ 同组「句准率」均带出）
    expect(screen.getByText('字准率')).toBeInTheDocument()
    expect(screen.getByText('句准率')).toBeInTheDocument()
    // 不相关维度不渲染
    expect(screen.queryByText('语义理解')).not.toBeInTheDocument()
  })

  it('搜索命中子维度后清空搜索恢复全量渲染', () => {
    setup()
    typeSearch('字准率')
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    typeSearch('')
    // 全量主维度恢复渲染
    expect(screen.getByText('语义理解')).toBeInTheDocument()
    expect(screen.getByText('唤醒成功率')).toBeInTheDocument()
  })

  it('搜索无命中显示「没有匹配的评估维度」空态（P2-1：子维度命中但主维度集为空时非空白）', () => {
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
})
