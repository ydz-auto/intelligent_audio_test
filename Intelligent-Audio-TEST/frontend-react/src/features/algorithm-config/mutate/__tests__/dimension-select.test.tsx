/**
 * DimensionSelect 未匹配存量值兜底测试（INT-1160 返工 P2）：
 * 评估映射/关联维度指向已删除维度时，触发器回退显示「维度(id)」（与分组头 evalGroupName、
 * 详情 §7.2 静态表同口径），而非裸 id，满足验收「真实数据下无裸 id」。
 */
import { render, screen } from '@testing-library/react'
import type { ComponentProps, ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import { DimensionSelect } from '../dimension-select'

const DIMENSIONS: Dimension[] = [
  { id: 1, name: '识别准确率', dimensionType: 'main', parentDimensionId: null, categoryId: 1 },
  { id: 2, name: '响应延迟', dimensionType: 'main', parentDimensionId: null, categoryId: 1 },
]

const CATEGORIES: EvaluationCategory[] = [{ id: 1, name: '基础质量' }]

/**
 * 三用例共用的基础 props：刻意不传 valueOf，走组件缺省 dimId 提取器（INT-1160 返工 P2 口径）。
 */
const baseProps = {
  dimensions: DIMENSIONS,
  categories: CATEGORIES,
  onValueChange: () => {},
  placeholder: '选择维度',
} satisfies Omit<ComponentProps<typeof DimensionSelect>, 'value' | 'valueOf'>

/**
 * 组件把可选 prop 命名为 valueOf，与 Object.prototype.valueOf 同名：TS 比对 JSX 属性时
 * 会把继承来的 valueOf(): Object 当成该 prop 参与检查，缺省不传即报 TS2322（INT-1823）。
 * 这里只把类型收窄成「不含 valueOf 的 props」，运行时仍是同一个组件，
 * 三个用例走的都是「未传 valueOf → 组件内回退 dimId」的真实路径，覆核口径不变。
 */
const DimensionSelectNoValueOf = DimensionSelect as unknown as (
  props: Omit<ComponentProps<typeof DimensionSelect>, 'valueOf'>
) => ReactNode

describe('DimensionSelect 未匹配存量值兜底（INT-1160 返工 P2）', () => {
  it('已删除维度值回退显示「维度(id)」而非裸 id', () => {
    render(<DimensionSelectNoValueOf {...baseProps} value='26' />)
    const trigger = screen.getByRole('combobox', { name: '评估维度' })
    expect(trigger).toHaveTextContent('维度(26)')
    // 不是裸 id（单元格不再显示原始枚举值/裸 id）
    expect(trigger.textContent?.trim()).not.toBe('26')
  })

  it('命中维度显示维度名（不加「维度(id)」前缀）', () => {
    render(<DimensionSelectNoValueOf {...baseProps} value='1' />)
    const trigger = screen.getByRole('combobox', { name: '评估维度' })
    expect(trigger).toHaveTextContent('识别准确率')
    expect(trigger).not.toHaveTextContent('维度(1)')
  })

  it('空值显示占位符', () => {
    render(<DimensionSelectNoValueOf {...baseProps} value='' />)
    const trigger = screen.getByRole('combobox', { name: '评估维度' })
    expect(trigger).toHaveTextContent('选择维度')
  })
})
