/**
 * 评估维度页分组视图单元测试（INT-1550）。
 * 空分类（维度已删光）仍渲染分组卡，「删除分类」入口可达；分类下有维度（含
 * 被筛选隐藏）时删除钮保持禁用——可删除判定按分类维度总数而非筛选后可见数。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import {
  GroupedDimensionList,
  type DimensionGroup,
} from '@/features/evaluation/components/grouped-dimension-list'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'

const category: EvaluationCategory = {
  id: 7,
  name: '识别质量',
  description: '',
  icon: 'fas fa-folder',
}

const dimension: Dimension = {
  id: 1,
  name: '识别准确率',
  description: '',
  dimensionType: 'main',
  parentDimensionId: null,
  categoryId: 7,
  weight: 5,
  status: true,
}

function renderList(groups: DimensionGroup[]) {
  const onDeleteCategory = vi.fn()
  render(
    <GroupedDimensionList
      groups={groups}
      selectedIds={new Set()}
      onToggleSelection={() => {}}
      canManage
      canRead
      canMoveUp={() => false}
      canMoveDown={() => false}
      weightPendingIds={new Set()}
      onEdit={() => {}}
      onDelete={() => {}}
      onDuplicate={() => {}}
      onAddSub={() => {}}
      onTestApi={() => {}}
      onRuleCalc={() => {}}
      onToggleStatus={() => {}}
      onMove={() => {}}
      onWeightCommit={() => {}}
      onAddDimension={() => {}}
      onEditCategory={() => {}}
      onDeleteCategory={onDeleteCategory}
    />
  )
  return { onDeleteCategory }
}

describe('GroupedDimensionList 空分类删除入口（INT-1550）', () => {
  it('空分类分组仍渲染：删除钮可用并触发 onDeleteCategory', async () => {
    const user = userEvent.setup()
    const { onDeleteCategory } = renderList([
      { key: '7', category, items: [], totalCount: 0 },
    ])

    expect(screen.getByText('识别质量')).toBeInTheDocument()
    expect(screen.getByText('该分类下暂无维度')).toBeInTheDocument()

    const deleteButton = screen.getByRole('button', {
      name: '删除分类 识别质量',
    })
    expect(deleteButton).toBeEnabled()
    await user.click(deleteButton)
    expect(onDeleteCategory).toHaveBeenCalledWith(category)
  })

  it('分类下有维度时删除钮禁用（即使筛选后组内为空）', () => {
    renderList([
      {
        key: '7',
        category,
        items: [],
        totalCount: 2,
      },
    ])

    expect(screen.getByText('0/2')).toBeInTheDocument()
    expect(screen.getByText('当前筛选下无匹配维度')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '删除分类 识别质量' })
    ).toBeDisabled()
  })

  it('有维度的分类渲染组内维度表格', () => {
    renderList([
      {
        key: '7',
        category,
        items: [
          { ...dimension, _level: 0, _isMain: true, _parentName: '' },
        ],
        totalCount: 1,
      },
    ])

    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '删除分类 识别质量' })
    ).toBeDisabled()
  })
})
