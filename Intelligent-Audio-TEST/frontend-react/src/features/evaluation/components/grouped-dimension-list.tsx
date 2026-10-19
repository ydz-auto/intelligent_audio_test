/**
 * 评估维度页分组视图（features/evaluation；11_用例域.md §4.1 分组视图）。
 * 按分类聚合卡（Collapsible 组头：分类 icon + 组名 + 计数 Badge + 描述 + 组内全选
 * Checkbox + 「添加维度」钮 + 分类行操作「编辑分类/删除分类」ghost 钮）。
 * 分类删除前拦截：分类下含维度时删除钮禁用 + Tooltip；组内嵌同款维度表格。
 */
import { ChevronDown, Folder, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DimensionTable,
  type HierarchicalDimension,
} from '@/features/evaluation/components/dimension-table'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import { cn } from '@/lib/utils'

export interface DimensionGroup {
  key: string
  category: EvaluationCategory | null
  items: HierarchicalDimension[]
}

export function GroupedDimensionList({
  groups,
  selectedIds,
  onToggleSelection,
  canManage,
  canRead,
  canMoveUp,
  canMoveDown,
  weightPendingIds,
  algorithmLabels,
  onEdit,
  onDelete,
  onDuplicate,
  onAddSub,
  onTestApi,
  onRuleCalc,
  onToggleStatus,
  onMove,
  onWeightCommit,
  onAddDimension,
  onEditCategory,
  onDeleteCategory,
}: {
  groups: DimensionGroup[]
  selectedIds: Set<number | string>
  onToggleSelection: (id: number | string) => void
  canManage: boolean
  canRead: boolean
  canMoveUp: (dimension: HierarchicalDimension) => boolean
  canMoveDown: (dimension: HierarchicalDimension) => boolean
  weightPendingIds: Set<number | string>
  /** 算法类型码 → 中文名（真实 /algorithm/options 的 value→label；组内表格徽章用） */
  algorithmLabels?: Record<string, string>
  onEdit: (dimension: Dimension) => void
  onDelete: (dimension: Dimension) => void
  onDuplicate: (dimension: Dimension) => void
  onAddSub: (dimension: Dimension) => void
  onTestApi: (dimension: Dimension) => void
  onRuleCalc: (dimension: Dimension) => void
  onToggleStatus: (dimension: Dimension) => void
  onMove: (dimension: Dimension, direction: -1 | 1) => void
  onWeightCommit: (dimension: Dimension, weight: number) => void
  onAddDimension: (category: EvaluationCategory | null) => void
  onEditCategory: (category: EvaluationCategory) => void
  onDeleteCategory: (category: EvaluationCategory) => void
}) {
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set())

  const toggleCollapsed = (key: string) => {
    setCollapsedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className='flex flex-col gap-3'>
      {groups.map((group) => {
        const key = group.key
        const collapsed = collapsedKeys.has(key)
        const groupAllSelected =
          group.items.length > 0 &&
          group.items.every((item) => selectedIds.has(item.id))
        const canDeleteCategory =
          !!group.category && group.items.length === 0

        return (
          <div
            key={key}
            className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'
          >
            {/* 组头 */}
            <div className='border-border/50 flex items-center gap-2 border-b px-3 py-2'>
              <Checkbox
                aria-label={`全选分组 ${group.category?.name ?? '未分类'}`}
                checked={groupAllSelected}
                onCheckedChange={() => {
                  if (groupAllSelected) {
                    group.items.forEach((item) => {
                      if (selectedIds.has(item.id))
                        onToggleSelection(item.id)
                    })
                  } else {
                    group.items.forEach((item) => {
                      if (!selectedIds.has(item.id))
                        onToggleSelection(item.id)
                    })
                  }
                }}
              />
              <button
                type='button'
                onClick={() => toggleCollapsed(key)}
                aria-expanded={!collapsed}
                className='flex min-w-0 flex-1 items-center gap-2 text-start'
              >
                <ChevronDown
                  aria-hidden='true'
                  className={cn(
                    'text-muted-foreground size-4 transition-transform',
                    collapsed && '-rotate-90'
                  )}
                />
                <Folder
                  aria-hidden='true'
                  className='text-muted-foreground size-4 shrink-0'
                />
                <span className='min-w-0 flex-1 truncate font-medium'>
                  {group.category?.name ?? '未分类'}
                </span>
                <span className='bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 text-xs tabular-nums'>
                  {group.items.length}
                </span>
                {group.category?.description && (
                  <span className='text-muted-foreground hidden truncate text-xs sm:inline'>
                    {group.category.description}
                  </span>
                )}
              </button>
              <div className='flex shrink-0 items-center gap-1'>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <span
                        tabIndex={0}
                        className={cn('inline-flex', !canManage && 'cursor-not-allowed')}
                      >
                        <Button
                          variant='outline'
                          size='sm'
                          className='h-7 gap-1.5'
                          disabled={!canManage}
                          onClick={() => onAddDimension(group.category)}
                        >
                          <Plus aria-hidden='true' className='size-3.5' />
                          添加维度
                        </Button>
                      </span>
                    }
                  />
                  <TooltipContent>
                    {canManage ? '添加维度' : '无 evaluation:dim_manage 权限'}
                  </TooltipContent>
                </Tooltip>
                {group.category && (
                  <>
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Button
                            variant='ghost'
                            size='icon-sm'
                            aria-label={`编辑分类 ${group.category.name}`}
                            disabled={!canManage}
                            onClick={() => onEditCategory(group.category!)}
                          >
                            <Pencil aria-hidden='true' className='size-3.5' />
                          </Button>
                        }
                      />
                      <TooltipContent>
                        {canManage ? '编辑分类' : '无 evaluation:category_manage 权限'}
                      </TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <span
                            tabIndex={0}
                            className={cn(
                              'inline-flex cursor-not-allowed',
                              (canDeleteCategory || !canManage) && 'inline-flex'
                            )}
                          >
                            <Button
                              variant='ghost'
                              size='icon-sm'
                              className='text-destructive'
                              aria-label={`删除分类 ${group.category.name}`}
                              disabled={!canManage || !canDeleteCategory}
                              onClick={() => onDeleteCategory(group.category!)}
                            >
                              <Trash2 aria-hidden='true' className='size-3.5' />
                            </Button>
                          </span>
                        }
                      />
                      <TooltipContent>
                        {!canDeleteCategory
                          ? `该分类下还有 ${group.items.length} 个维度，请先迁移或删除维度`
                          : !canManage
                            ? '无 evaluation:category_manage 权限'
                            : '删除分类'}
                      </TooltipContent>
                    </Tooltip>
                  </>
                )}
              </div>
            </div>

            {/* 组内容（组内嵌同款表格） */}
            {!collapsed && (
              <div className='p-3'>
                <DimensionTable
                  items={group.items}
                  selectedIds={selectedIds}
                  onToggleSelection={onToggleSelection}
                  showHeaderCheckbox={false}
                  categories={group.category ? [group.category] : []}
                  canManage={canManage}
                  canRead={canRead}
                  canMoveUp={canMoveUp}
                  canMoveDown={canMoveDown}
                  weightPendingIds={weightPendingIds}
                  algorithmLabels={algorithmLabels}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  onDuplicate={onDuplicate}
                  onAddSub={onAddSub}
                  onTestApi={onTestApi}
                  onRuleCalc={onRuleCalc}
                  onToggleStatus={onToggleStatus}
                  onMove={onMove}
                  onWeightCommit={onWeightCommit}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
