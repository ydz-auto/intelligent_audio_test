/**
 * 日志批量操作浮条（interfaces 层；17_配置运维.md §4.5 logs-bulk-actions）。
 * 勾选≥1 浮起（floating bottom + backdrop-blur）；计数「已选择 {n} 条日志」+
 * 「标记颜色」DropdownMenu（黄/红/绿/蓝 → PUT /logs/mark，log:manage）+
 * 「复制内容」（log:read，拼接复制）+「导出选中」（POST /logs/export{log_ids}，
 * log:read）+「清除选中」（§12-5 后端 clear 无按 log_ids 批量删除缺口 → disabled
 * + Tooltip「按条件清除」）。
 */
import { Copy, Download, Flag, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { LOG_MARK_COLORS } from '@/features/logs/constants'

export type LogsBulkActionsProps = {
  count: number
  canManage: boolean
  onBatchMark: (mark: string) => void
  onCopySelected: () => void
  onExportSelected: () => void
}

export function LogsBulkActions(props: LogsBulkActionsProps) {
  return (
    <div className='bg-background/95 shadow-xl flex flex-wrap items-center justify-between gap-2 rounded-xl border p-2 backdrop-blur-lg'>
      <span className='text-muted-foreground px-1 text-sm tabular-nums'>
        已选择 {props.count} 条日志
      </span>
      <div className='flex flex-wrap items-center gap-1.5'>
        {props.canManage && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant='outline' size='sm' className='h-7 gap-1.5 text-xs'>
                  <Flag aria-hidden='true' className='size-3.5' />
                  标记颜色
                </Button>
              }
            />
            <DropdownMenuContent align='end' className='w-44'>
              {/* base-ui 的 GroupLabel 必须挂在 Group 下，否则渲染即抛错（整页错误页） */}
              <DropdownMenuGroup>
                <DropdownMenuLabel>选择标记颜色</DropdownMenuLabel>
              </DropdownMenuGroup>
              {LOG_MARK_COLORS.map((color) => (
                <DropdownMenuItem
                  key={color.value}
                  onClick={() => props.onBatchMark(color.value)}
                >
                  <span
                    aria-hidden='true'
                    className={cn('size-2.5 rounded-full', color.swatch)}
                  />
                  {color.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        <Button
          variant='outline'
          size='sm'
          className='h-7 gap-1.5 text-xs'
          onClick={props.onCopySelected}
        >
          <Copy aria-hidden='true' className='size-3.5' />
          复制内容
        </Button>

        <Button
          variant='outline'
          size='sm'
          className='h-7 gap-1.5 text-xs'
          onClick={props.onExportSelected}
        >
          <Download aria-hidden='true' className='size-3.5' />
          导出选中
        </Button>

        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant='outline'
                size='sm'
                className='h-7 gap-1.5 text-xs'
                disabled
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
                清除选中
              </Button>
            }
          />
          <TooltipContent>
            清除接口仅支持按时间条件（§12-5 待后端扩展 log_ids 批量删除）
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  )
}
