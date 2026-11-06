/**
 * 报告列表分页（对位 newAPI DataTablePagination 语义，规范 §3.9）：
 * 页码导航 + 每页条数 Select[10,20,30,40,50,100]（默认 20，服务端分页 manualPagination）。
 */
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { getPageNumbers } from '@/lib/utils'
import { cn } from '@/lib/utils'

export const REPORT_PAGE_SIZE_OPTIONS = [10, 20, 30, 40, 50, 100] as const

interface ReportsPaginationProps {
  page: number
  pageSize: number
  total: number
  pages: number
  /** 计数文案实体名（报告列表「报告」/用例列表「用例」） */
  entityLabel?: string
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

export function ReportsPagination({
  page,
  pageSize,
  total,
  pages,
  entityLabel = '报告',
  onPageChange,
  onPageSizeChange,
}: ReportsPaginationProps) {
  if (total === 0) return null
  const numbers = getPageNumbers(page, pages)

  return (
    <div className='flex min-w-0 flex-wrap items-center justify-between gap-3'>
      <div className='text-muted-foreground flex items-center gap-2 text-sm'>
        <span>
          共 <span className='text-foreground font-semibold tabular-nums'>{total}</span> 个{entityLabel}
        </span>
        <Select
          value={String(pageSize)}
          onValueChange={(v) => onPageSizeChange(Number(v))}
        >
          <SelectTrigger
            size='sm'
            aria-label='每页条数'
            className='text-foreground h-8 w-[64px] font-medium tabular-nums sm:w-[70px]'
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent align='end'>
            {REPORT_PAGE_SIZE_OPTIONS.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size} / 页
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <nav aria-label='分页' className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='icon-sm'
          disabled={page <= 1}
          aria-label='上一页'
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className='size-4' />
        </Button>
        {numbers.map((item, index) =>
          item === '...' ? (
            <span key={`dots-${index}`} className='text-muted-foreground px-1 text-sm'>
              …
            </span>
          ) : (
            <Button
              key={item}
              variant={item === page ? 'default' : 'outline'}
              size='icon-sm'
              className={cn('min-w-8 px-2 tabular-nums')}
              aria-current={item === page ? 'page' : undefined}
              onClick={() => onPageChange(Number(item))}
            >
              {item}
            </Button>
          )
        )}
        <Button
          variant='outline'
          size='icon-sm'
          disabled={page >= pages}
          aria-label='下一页'
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className='size-4' />
        </Button>
      </nav>
    </div>
  )
}
