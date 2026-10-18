/**
 * 已选汇总条（18_挑选合并交互重设计.md §3.3/§7.1，INT-600）。
 * DataTableBulkActions 形态 sticky bottom：已选规模 + 全选当前筛选/反选/清空 + 加入购物车。
 */
import { ShoppingCart, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { SelectionStats } from '@/domain/lib/cherry-pick-tree'

export interface SelectedSummaryBarProps {
  stats: SelectionStats
  hasVisibleItems: boolean
  onSelectAll: () => void
  onInvert: () => void
  onClear: () => void
  onAddToCart: () => void
  adding?: boolean
}

/** 已选汇总条（sticky bottom，跨筛选保留已勾选，§6.2） */
export function SelectedSummaryBar({
  stats,
  hasVisibleItems,
  onSelectAll,
  onInvert,
  onClear,
  onAddToCart,
  adding,
}: SelectedSummaryBarProps) {
  const empty = stats.results === 0
  return (
    <div className='fixed bottom-6 left-1/2 z-40 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
      <div className='bg-background/95 supports-backdrop-filter:bg-background/60 flex items-center gap-1 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
        <Button
          variant='ghost'
          size='icon-sm'
          aria-label='清空选择'
          disabled={empty}
          onClick={onClear}
        >
          <X aria-hidden='true' />
        </Button>
        <Separator orientation='vertical' className='h-5' />
        <Badge className='min-w-8 justify-center rounded-lg'>
          {stats.results}
        </Badge>
        <span className='text-sm whitespace-nowrap'>
          已选 {stats.results} 条结果 · 来自 {stats.tasks} 个任务 · 覆盖{' '}
          {stats.devices} 台设备
        </span>
        <Separator orientation='vertical' className='h-5' />
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size='sm'
                variant='outline'
                disabled={!hasVisibleItems}
                onClick={onSelectAll}
              >
                全选当前筛选
              </Button>
            }
          />
          <TooltipContent>
            候选按页加载（每页至多 200 条），仅覆盖当前已加载的候选；跨页全选待后端聚合端点（§11-4）落地
          </TooltipContent>
        </Tooltip>
        <Button
          size='sm'
          variant='outline'
          disabled={!hasVisibleItems}
          onClick={onInvert}
        >
          反选
        </Button>
        <Button
          size='sm'
          variant='outline'
          disabled={!hasVisibleItems}
          onClick={onClear}
        >
          清空
        </Button>
        <Button
          size='sm'
          className='gap-1.5'
          disabled={empty}
          onClick={onAddToCart}
        >
          <ShoppingCart aria-hidden='true' className='size-3.5' />
          {adding ? '加入中…' : `加入购物车（${stats.results}）`}
        </Button>
      </div>
    </div>
  )
}
