/**
 * 批量复核浮条（19 规范 §3.1/§3.3，DataTableBulkActions 形态）。
 * 任务详情「关联用例」勾选多行 → 底部浮条「批量复核」；同一改判字段应用到全部勾选结果，
 * 后端逐条留痕（未终态/同值条目自动跳过并提示）。
 * 浮条样式照搬 09_任务域.md §3.10（task-bulk-actions）。
 */
import { X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export function ManualReviewBatchBar({
  selectedCount,
  onClear,
  onBatchReview,
  disabled,
}: {
  selectedCount: number
  onClear: () => void
  onBatchReview: () => void
  /** 批量复核禁用（如任务未到终态 / 无权限已在入口隐藏） */
  disabled?: boolean
}) {
  if (selectedCount === 0) return null
  return (
    <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
      <div className='bg-background/95 supports-backdrop-filter:bg-background/60 flex items-center gap-1 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant='ghost'
                size='icon-sm'
                aria-label='清除选择 (Esc)'
                onClick={onClear}
              />
            }
          >
            <X aria-hidden='true' />
          </TooltipTrigger>
          <TooltipContent>清除选择 (Esc)</TooltipContent>
        </Tooltip>
        <Separator orientation='vertical' className='h-5' />
        <Badge className='min-w-8 justify-center rounded-lg'>{selectedCount}</Badge>
        <span className='text-sm'>条用例已选择</span>
        <Separator orientation='vertical' className='h-5' />
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size='sm'
                variant='outline'
                disabled={disabled}
                onClick={onBatchReview}
              />
            }
          >
            批量复核
          </TooltipTrigger>
          <TooltipContent>同一改判字段应用到全部勾选结果，逐条留痕，未终态或同值条目自动跳过并提示</TooltipContent>
        </Tooltip>
      </div>
    </div>
  )
}
