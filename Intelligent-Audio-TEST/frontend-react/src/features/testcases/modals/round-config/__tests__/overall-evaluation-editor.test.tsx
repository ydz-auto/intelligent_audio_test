/**
 * 整体评估维度编辑器测试（11_用例域.md §5.1.3.1）：
 * 启用开关默认开（V9.7.10 OverallEvaluationEditor.vue `enabled = ref(true)`）；
 * 存量用例的 config.dimensions 由抽屉在 useEffect 里晚一步回填——挂载时 value 还是空数组，
 * 回填后开关必须自动为开、维度勾选与参数卡完整呈现（INT-1424 终审 P2-1 回归）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { TestCaseDimensionItem } from '@/domain/models/evaluationStrategy'
import { OverallEvaluationEditor } from '@/features/testcases/modals/round-config/overall-evaluation-editor'
import {
  MOCK_CASE_DIMENSIONS,
  MOCK_EVALUATION_CATEGORIES,
} from '@/infrastructure/mock/testcases-mock'

const EXISTING_DIMS: TestCaseDimensionItem[] = [
  { id: 1, name: '识别准确率', weight: 60, threshold: 85 },
]

const renderEditor = (value: TestCaseDimensionItem[] = []) => {
  const onChange = vi.fn()
  const utils = render(
    <OverallEvaluationEditor
      dimensions={MOCK_CASE_DIMENSIONS}
      categories={MOCK_EVALUATION_CATEGORIES}
      value={value}
      onChange={onChange}
    />
  )
  return { ...utils, onChange }
}

/** base-ui Switch：role=switch + aria-checked（兼容 data-checked 属性） */
const isSwitchOn = () => {
  const node = screen.getByRole('switch', { name: '启用整体评估' })
  return (
    node.getAttribute('aria-checked') === 'true' ||
    node.hasAttribute('data-checked')
  )
}

describe('OverallEvaluationEditor', () => {
  it('新增用例默认启用整体评估（维度多选可见）', () => {
    renderEditor([])
    expect(isSwitchOn()).toBe(true)
    expect(screen.getByPlaceholderText('搜索评估维度')).toBeInTheDocument()
  })

  it('挂载时 value 为空、随后回填 config.dimensions → 开关为开且维度参数卡完整回显', () => {
    const { rerender } = renderEditor([])
    // 抽屉回填前：开关默认开，但还没有已选维度参数卡
    expect(screen.queryByText('权重')).not.toBeInTheDocument()

    // 抽屉 useEffect 回填（模拟：同一组件实例拿到非空 value）
    rerender(
      <OverallEvaluationEditor
        dimensions={MOCK_CASE_DIMENSIONS}
        categories={MOCK_EVALUATION_CATEGORIES}
        value={EXISTING_DIMS}
        onChange={vi.fn()}
      />
    )

    expect(isSwitchOn()).toBe(true)
    expect(screen.getByPlaceholderText('搜索评估维度')).toBeInTheDocument()
    // 已选维度参数卡（DimensionParamCard：权重/阈值）回显
    expect(screen.getAllByText('识别准确率').length).toBeGreaterThan(0)
    expect(screen.getByText('权重')).toBeInTheDocument()
    expect(screen.getByText('阈值')).toBeInTheDocument()
  })

  it('关闭启用开关 → emit 空数组（保存即清除整体评估维度）', () => {
    const { onChange } = renderEditor(EXISTING_DIMS)
    fireEvent.click(screen.getByRole('switch', { name: '启用整体评估' }))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
