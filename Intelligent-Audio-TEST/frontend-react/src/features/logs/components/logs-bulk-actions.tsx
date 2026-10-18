/**
 * 日志批量操作浮条（features/logs；17_配置运维.md §4.5）。
 * 勾选≥1 行浮起：计数「已选择 {n} 条日志」+ 标记颜色（log:manage）+ 复制内容 +
 * 导出选中（log:read）+ 清除选中（后端按所选删除为缺口 §12-5，禁用并 Tooltip「按条件清除」）。
 */
import { Copy, FileDown, Tag } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { LOG_MARK_OPTIONS } from '@/domain/models/log'
import { LOG_MARK_META } from '@/features/logs/constants'
import { cn } from '@/lib/utils'

export type LogsBulkActionsProps = {
  count: number
  canManage: boolean
  onMarkColor: (color: string) => void
  onCopySelected: () => void
  onExportSelected: () => void
}

export function LogsBulkActions({
  count,
  canManage,
  onMarkColor,
  onCopySelected,
  onExportSelected,
}: LogsBulkActionsProps) {
  const [open, setOpen] = useState(false)
  return (
    <div className='shadow-xl flex items-center justify-between gap-2 rounded-xl border bg-background/95 p-2 backdrop-blur-lg'>
      <span className='text-muted-foreground px-1 text-sm tabular-nums'>
        已选择 {count} 条日志
      </span>
      <div className='flex flex-wrap items-center gap-1.5'>
        {canManage && (
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
              render={
                <Button variant='outline' size='sm' className='gap-1.5'>
                  <Tag aria-hidden='true' className='size-3.5' />
                  标记颜色
                </Button>
              }
            />
            <PopoverContent className='w-36 p-1.5'>
              <div className='grid gap-0.5'>
                {LOG_MARK_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type='button'
                    className='hover:bg-muted flex items-center gap-2 rounded-md px-2 py-1.5 text-xs'
                    onClick={() => {
                      onMarkColor(option.value)
                      setOpen(false)
                    }}
                  >
                    <span
                      aria-hidden='true'
                      className={cn('size-2.5 rounded-full', LOG_MARK_META[option.value]?.dotClass)}
                    />
                    {option.label}
                  </button>
                ))}
              </div>
            </PopoverContent>
          </Popover>
        )}
        <Button variant='outline' size='sm' className='gap-1.5' onClick={onCopySelected}>
          <Copy aria-hidden='true' className='size-3.5' />
          复制内容
        </Button>
        <Button variant='outline' size='sm' className='gap-1.5' onClick={onExportSelected}>
          <FileDown aria-hidden='true' className='size-3.5' />
          导出选中
        </Button>
        <TooltipProvider delay={100}>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button variant='outline' size='sm' className='gap-1.5' disabled>
                  清除选中
                </Button>
              }
            />
            <TooltipContent>批量删除所选为后端缺口，请按条件清除（页头「清除日志」）</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  )
}
