/**
 * 分页脚注（09_任务域.md §3.11，PageFooterPortal 落 SectionPageLayout 页脚）。
 * 「共 {n} 条」+ 每页 Select（[10,20,30,40,50,100]）+ 首页/上一页/页码/下一页/末页。
 * mock 态为演示控件（接线后 URL 化：page/pageSize 进 search）。
 */
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { useState } from 'react'

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

export function TasksPagination({ total }: { total: number }) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  const goto = (next: number) => setPage(Math.min(pageCount, Math.max(1, next)))

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
                setPageSize(Number(v))
                setPage(1)
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
              disabled={page <= 1}
              onClick={() => goto(1)}
            >
              <ChevronsLeft aria-hidden='true' />
            </Button>
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='上一页'
              disabled={page <= 1}
              onClick={() => goto(page - 1)}
            >
              <ChevronLeft aria-hidden='true' />
            </Button>
            {Array.from({ length: pageCount }, (_, i) => i + 1)
              .slice(Math.max(0, page - 3), page + 2)
              .map((p) => (
                <Button
                  key={p}
                  variant={p === page ? 'default' : 'ghost'}
                  size='sm'
                  className={cn(
                    'h-8 min-w-8 px-2 tabular-nums',
                    p === page && 'font-semibold'
                  )}
                  onClick={() => goto(p)}
                >
                  {p}
                </Button>
              ))}
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='下一页'
              disabled={page >= pageCount}
              onClick={() => goto(page + 1)}
            >
              <ChevronRight aria-hidden='true' />
            </Button>
            <Button
              variant='ghost'
              size='icon-xs'
              aria-label='末页'
              disabled={page >= pageCount}
              onClick={() => goto(pageCount)}
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
