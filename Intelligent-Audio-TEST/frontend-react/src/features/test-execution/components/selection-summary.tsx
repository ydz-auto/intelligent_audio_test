/**
 * SelectionSummary 已选汇总条（interfaces/features/test-execution/components；步骤二/三共用，
 * 10_测试执行.md §3.5/§3.6.3）。
 * 用例态：常驻「已选 {n} 条用例」+ Badge（手动勾选 a · 反选补齐 b）+「清空选择」+
 * 提示「未选择用例时，将按当前筛选条件使用全部 {total} 条用例」（info 色）。
 * 资源态：明细 Popover（名称+状态；可单项移除 ×）。
 */
import { Info, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'

interface SelectionSummaryProps {
  /** 用例汇总 | 资源汇总 */
  mode: 'case' | 'resource'
  /** 已选数量 */
  count: number
  /** 用例：手动勾选/反选补齐计数；资源：空 */
  manual?: number
  invertAdded?: number
  onClear: () => void
  /** 用例：未手动选择时的全量 total；资源：不展示 */
  total?: number
  /** 资源：单位文案（「台设备」/「个 API」） */
  unitText?: string
  /** 资源：并发补充（API 页「· 并发上限 {sum}」） */
  concurrencyText?: string
  /** 资源明细项（名称+状态+移除） */
  items?: Array<{ id: number; name: string; status: string | null }>
  onRemoveItem?: (id: number) => void
  className?: string
}

export function SelectionSummary({
  mode,
  count,
  manual,
  invertAdded,
  onClear,
  total,
  unitText,
  concurrencyText,
  items = [],
  onRemoveItem,
  className,
}: SelectionSummaryProps) {
  if (mode === 'resource') {
    return (
      <div
        className={cn(
          'flex flex-wrap items-center gap-2 rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-sm',
          className
        )}
      >
        <span>
          已选 <span className='font-medium tabular-nums'>{count}</span>{' '}
          {unitText ?? '项'}
          {concurrencyText && (
            <span className='text-muted-foreground ms-2 text-xs'>
              · {concurrencyText}
            </span>
          )}
        </span>
        {items.length > 0 && (
          <Popover>
            <PopoverTrigger render={<Button variant='ghost' size='sm' className='h-6 text-xs' />}>
              明细
            </PopoverTrigger>
            <PopoverContent align='start' className='w-64 p-1'>
              <ul className='max-h-64 overflow-auto'>
                {items.map((item) => (
                  <li
                    key={item.id}
                    className='hover:bg-accent flex items-center justify-between gap-2 rounded-md px-2 py-1.5'
                  >
                    <span className='min-w-0 truncate text-sm'>{item.name}</span>
                    <span className='flex shrink-0 items-center gap-1'>
                      <StatusBadge
                        label={item.status === 'online' ? '在线' : '离线'}
                        variant={item.status === 'online' ? 'success' : 'neutral'}
                      />
                      {onRemoveItem && (
                        <button
                          type='button'
                          aria-label={`移除 ${item.name}`}
                          className='text-muted-foreground hover:text-destructive rounded p-0.5'
                          onClick={() => onRemoveItem(item.id)}
                        >
                          <X aria-hidden='true' className='size-3.5' />
                        </button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
        )}
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground ml-auto h-6 text-xs'
          onClick={onClear}
        >
          清空选择
        </Button>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-sm',
        className
      )}
    >
      <span>
        已选 <span className='font-medium tabular-nums'>{count}</span> 条用例
      </span>
      <Badge variant='secondary' className='rounded-md text-[11px]'>
        手动勾选 {manual ?? 0} · 反选补齐 {invertAdded ?? 0}
      </Badge>
      <Button
        variant='ghost'
        size='sm'
        className='text-muted-foreground h-6 text-xs'
        onClick={onClear}
      >
        清空选择
      </Button>
      {count === 0 && typeof total === 'number' && (
        <span className='text-info flex items-center gap-1 text-xs'>
          <Info aria-hidden='true' className='size-3.5' />
          未选择用例时，将按当前筛选条件使用全部 {total} 条用例
        </span>
      )}
    </div>
  )
}
