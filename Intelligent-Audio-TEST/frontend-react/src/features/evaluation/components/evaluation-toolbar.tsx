/**
 * 评估维度页筛选工具栏（features/evaluation；11_用例域.md §4.1 筛选行）。
 * 搜索（名称/描述/keywords）+ 状态 facet + 分类 facet + 关联算法 facet（与全局算法
 * 切换器联动：全局算法非空时 facet 默认值取全局算法并显示只读联动 chip，× 清空回到
 * 页内自由筛选；用户显式选择 facet 即脱离全局）+ 重置筛选。
 * algorithmFilter=用户显式页内值（isFiltered/重置判定），algorithmFacetValue=实际生效值
 * （显式值优先，否则继承全局算法）。
 */
import { Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ALGORITHM_FILTER_ALL_LABEL,
  CATEGORY_FILTER_ALL_LABEL,
  DIMENSION_SEARCH_PLACEHOLDER,
  STATUS_FILTER_OPTIONS,
} from '@/features/evaluation/constants'
import { FacetFilter } from '@/features/evaluation/components/evaluation-facet'
import type { EvaluationCategory } from '@/domain/models/evaluationDimension'

export function EvaluationToolbar({
  searchValue,
  onSearch,
  statusFilter,
  onStatusFilter,
  categoryFilter,
  onCategoryFilter,
  categories,
  algorithmFilter,
  algorithmFacetValue,
  onAlgorithmFilter,
  algorithmOptions,
  globalAlgorithmLabel,
  onClearGlobalAlgorithm,
  canFilter,
  onReset,
}: {
  searchValue: string
  onSearch: (value: string) => void
  statusFilter: string
  onStatusFilter: (value: string) => void
  categoryFilter: string
  onCategoryFilter: (value: string) => void
  categories: EvaluationCategory[]
  algorithmFilter: string
  /** facet 实际生效值（显式选择优先，否则继承全局算法；无全局时 'all'） */
  algorithmFacetValue: string
  onAlgorithmFilter: (value: string) => void
  algorithmOptions: Array<{ value: string; label: string }>
  /** 全局算法名（联动 chip；null=无全局选择） */
  globalAlgorithmLabel: string | null
  onClearGlobalAlgorithm: () => void
  canFilter: boolean
  onReset: () => void
}) {
  const isFiltered =
    searchValue.trim() !== '' ||
    statusFilter !== 'all' ||
    categoryFilter !== 'all' ||
    algorithmFilter !== 'all'

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <div className='relative min-w-0 flex-1 basis-52'>
        <Search
          aria-hidden='true'
          className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
        />
        <Input
          aria-label='搜索评估维度'
          value={searchValue}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={DIMENSION_SEARCH_PLACEHOLDER}
          disabled={!canFilter}
          className='h-7 pl-8'
        />
      </div>

      <FacetFilter
        title='状态'
        allLabel='全部状态'
        options={STATUS_FILTER_OPTIONS.filter((o) => o.value !== 'all')}
        value={statusFilter}
        onValueChange={onStatusFilter}
        disabled={!canFilter}
      />

      <FacetFilter
        title='分类'
        allLabel={CATEGORY_FILTER_ALL_LABEL}
        options={categories.map((c) => ({ value: String(c.id), label: c.name }))}
        value={categoryFilter}
        onValueChange={onCategoryFilter}
        disabled={!canFilter}
      />

      {isFiltered && (
        <Button
          variant='ghost'
          size='sm'
          className='h-7 gap-1.5 px-2 text-muted-foreground'
          onClick={onReset}
        >
          <X aria-hidden='true' className='size-3.5' />
          重置筛选
        </Button>
      )}
    </div>
  )
}
