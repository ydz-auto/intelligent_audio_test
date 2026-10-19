/**
 * 分页脚注（09_任务域.md §3.11，PageFooterPortal 落 SectionPageLayout 页脚）。
 * 「共 {n} 条」+ 每页 Select（[10,20,30,40,50,100]）+ 首页/上一页/页码/下一页/末页。
 * 受控组件：page/pageSize 由页面态持有（接 useTasksList queryKey），切换即重新查询。
 */
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { cn } from '@/lib/utils'

const PAGE_SIZE_OPTIONS = [10, 20, 30, 40, 50, 100]

export function TasksPagination({
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  const safePage = Math.min(Math.max(1, page), pageCount)

  return (
    <PageFooterPortal>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <p className='text-muted-foreground text-xs tabular-nums'>
          共 {total} 条
        </p>
        <div className='flex flex-wrap items-center gap-2'>
          <div className='flex items-center gap-1.5'>
            <span className='text-muted-foreground text-xs'>每页</span>
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                onPageSizeChange(Number(v))
                onPageChange(1)
              }}
            >
              <SelectTrigger size='sm' className='h-8 w-[64px]' aria-label='每页条数'>
                <SelectValue>{pageSize}</SelectValue>
              </SelectTrigger>
              <SelectContent align='end'>
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='flex items-center gap-1'>
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='首页'
              disabled={safePage <= 1}
              onClick={() => onPageChange(1)}
            >
              <ChevronsLeft aria-hidden='true' />
            </Button>
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='上一页'
              disabled={safePage <= 1}
              onClick={() => onPageChange(safePage - 1)}
            >
              <ChevronLeft aria-hidden='true' />
            </Button>
            {Array.from({ length: pageCount }, (_, i) => i + 1)
              .slice(Math.max(0, safePage - 3), safePage + 2)
              .map((p) => (
                <Button
                  key={p}
                  variant={p === safePage ? 'default' : 'ghost'}
                  size='sm'
                  className={cn(
                    'h-8 min-w-8 px-2 tabular-nums',
                    p === safePage && 'font-semibold'
                  )}
                  onClick={() => onPageChange(p)}
                >
                  {p}
                </Button>
              ))}
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='下一页'
              disabled={safePage >= pageCount}
              onClick={() => onPageChange(safePage + 1)}
            >
              <ChevronRight aria-hidden='true' />
            </Button>
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='末页'
              disabled={safePage >= pageCount}
              onClick={() => onPageChange(pageCount)}
            >
              <ChevronsRight aria-hidden='true' />
            </Button>
          </div>
          <span className='text-muted-foreground text-xs tabular-nums'>
            {from}–{to} / {total}
          </span>
        </div>
      </div>
    </PageFooterPortal>
  )
}
