/**
 * 评估维度页确认文案（11_用例域.md §4.1/§5.6）单元测试。
 * 覆盖删除维度/批量启用/批量禁用/批量删除/删除分类/复制维度六态文案与 destructive 标志。
 */
import { describe, expect, it } from 'vitest'

import { buildConfirmCopy } from '@/features/evaluation/modals/evaluation-confirms'
import type { EvaluationConfirmState } from '@/features/evaluation/types'

const dimension = {
  id: 1,
  name: '识别准确率',
  dimensionType: 'main',
  parentDimensionId: null,
  categoryId: 1,
  weight: 9,
  status: true,
}

const category = { id: 1, name: '识别质量', description: '', icon: 'fas fa-folder' }

function state(kind: EvaluationConfirmState['kind'], extra: Partial<EvaluationConfirmState> = {}): EvaluationConfirmState {
  if (kind === 'delete-dimension') return { kind, dimension } as EvaluationConfirmState
  if (kind === 'delete-category') return { kind, category } as EvaluationConfirmState
  if (kind === 'duplicate-dimension') return { kind, dimension } as EvaluationConfirmState
  return { kind, action: 'enable', count: 3, ...extra } as EvaluationConfirmState
}

describe('buildConfirmCopy', () => {
  it('删除维度：标题/文案/destructive 逐字', () => {
    const copy = buildConfirmCopy(state('delete-dimension'))
    expect(copy.title).toBe('删除维度')
    expect(copy.desc).toBe('确定要删除维度「识别准确率」吗？此操作不可恢复。')
    expect(copy.confirmText).toBe('删除')
    expect(copy.destructive).toBe(true)
  })

  it('批量启用：文案含选中数量，非 destructive', () => {
    const copy = buildConfirmCopy({ kind: 'batch-action', action: 'enable', count: 3 })
    expect(copy.title).toBe('批量启用')
    expect(copy.desc).toBe('确定要启用选中的 3 个维度吗？')
    expect(copy.confirmText).toBe('批量启用')
    expect(copy.destructive).toBe(false)
  })

  it('批量禁用：文案含选中数量', () => {
    const copy = buildConfirmCopy({ kind: 'batch-action', action: 'disable', count: 5 })
    expect(copy.title).toBe('批量禁用')
    expect(copy.desc).toBe('确定要禁用选中的 5 个维度吗？')
    expect(copy.destructive).toBe(false)
  })

  it('批量删除：destructive 标志置真', () => {
    const copy = buildConfirmCopy({ kind: 'batch-action', action: 'delete', count: 2 })
    expect(copy.title).toBe('批量删除')
    expect(copy.desc).toBe('确定要删除选中的 2 个维度吗？')
    expect(copy.confirmText).toBe('批量删除')
    expect(copy.destructive).toBe(true)
  })

  it('删除分类：文案逐字', () => {
    const copy = buildConfirmCopy(state('delete-category'))
    expect(copy.title).toBe('删除分类')
    expect(copy.desc).toBe('确定删除分类「识别质量」吗？此操作不可恢复。')
    expect(copy.destructive).toBe(true)
  })

  it('复制维度：文案含深拷贝语义', () => {
    const copy = buildConfirmCopy(state('duplicate-dimension'))
    expect(copy.title).toBe('复制维度')
    expect(copy.desc).toContain('确定要复制维度「识别准确率」吗？')
    expect(copy.desc).toContain('深拷贝')
    expect(copy.confirmText).toBe('复制')
    expect(copy.destructive).toBe(false)
  })
})
