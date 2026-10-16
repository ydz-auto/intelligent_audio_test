/**
 * 分页条（§3.9 DataTablePagination 对位：共 {total} 条 · 每页 Select · 页码钮 h-8 min-w-8）。
 * 列表视图经 PageFooterPortal 落页脚；文件夹视图内嵌复用。
 */
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '@/features/audio-import/constants'

export type PaginationBarProps = {
  page: number
  pageCount: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

export function PaginationBar(props: PaginationBarProps) {
  return (
    <div className='flex flex-wrap items-center justify-end gap-2 text-sm'>
      <span className='text-muted-foreground tabular-nums'>共 {props.total} 条</span>
      <Select
        value={String(props.pageSize)}
        onValueChange={(value) =>
          props.onPageSizeChange(Number(value ?? DEFAULT_PAGE_SIZE))
        }
      >
        <SelectTrigger size='sm' className='w-24' aria-label='每页条数'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PAGE_SIZE_OPTIONS.map((size) => (
            <SelectItem key={size} value={String(size)}>
              {size} 条/页
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='sm'
          disabled={props.page <= 1}
          onClick={() => props.onPageChange(props.page - 1)}
        >
          上一页
        </Button>
        <span className='text-muted-foreground px-1 tabular-nums'>
          {props.page} / {props.pageCount}
        </span>
        <Button
          variant='outline'
          size='sm'
          disabled={props.page >= props.pageCount}
          onClick={() => props.onPageChange(props.page + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}
