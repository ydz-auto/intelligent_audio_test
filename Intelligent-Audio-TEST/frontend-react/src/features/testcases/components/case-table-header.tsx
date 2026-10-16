/**
 * 用例表格表头（11_用例域.md §3.3 列定义 + §1.3 视觉实测要点）：
 * 选择列（表头全选）+ 列头（名称/更新时间可排序演示控件）+ 视图选项下拉（列显隐）。
 * 表头底 `bg-[var(--table-header)]`、字号 text-xs；排序为演示控件（接线后接服务端 sortBy/sortOrder）。
 */
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  COLUMN_OPTIONS,
  type CaseColumnKey,
} from '@/features/testcases/constants'

function SortableHeader({ label, active }: { label: string; active?: boolean }) {
  return (
    <button
      type='button'
      className={cn(
        'hover:text-foreground inline-flex items-center gap-1 text-xs font-medium transition-colors',
        active ? 'text-foreground' : 'text-muted-foreground'
      )}
      title='演示排序控件（接线后接服务端 sortBy/sortOrder）'
    >
      {label}
      <span aria-hidden='true' className='text-muted-foreground/50 text-[10px]'>
        ⇅
      </span>
    </button>
  )
}

export function ViewOptions({
  visible,
  onChange,
}: {
  visible: Set<CaseColumnKey>
  onChange: (visible: Set<CaseColumnKey>) => void
}) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant='outline' size='sm' className='h-8 gap-1.5 px-2.5 font-normal' />
        }
      >
        <span className='text-muted-foreground'>视图</span>
        <span className='font-medium'>切换列</span>
      </PopoverTrigger>
      <PopoverContent align='end' className='min-w-40 p-1.5'>
        {COLUMN_OPTIONS.map((option) => {
          const checked = visible.has(option.key)
          return (
            <label
              key={option.key}
              className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors'
            >
              <Checkbox
                checked={checked}
                onCheckedChange={() => {
                  const next = new Set(visible)
                  if (checked) next.delete(option.key)
                  else next.add(option.key)
                  onChange(next)
                }}
              />
              {option.label}
            </label>
          )
        })}
      </PopoverContent>
    </Popover>
  )
}

export function CaseTableHeader({
  allChecked,
  onToggleAll,
  visible,
}: {
  allChecked: boolean
  onToggleAll: (checked: boolean) => void
  visible: Set<CaseColumnKey>
}) {
  const col = (key: CaseColumnKey) => visible.has(key)
  return (
    <thead>
      <tr className='bg-[var(--table-header)] text-xs'>
        <th className='w-11 px-3 py-2'>
          <Checkbox checked={allChecked} aria-label='全选' onCheckedChange={onToggleAll} />
        </th>
        {col('name') && (
          <th className='px-3 py-2 text-left font-medium'>
            <SortableHeader label='用例名称' active />
          </th>
        )}
        {col('type') && (
          <th className='px-3 py-2 text-left font-medium'>类型</th>
        )}
        {col('algorithm') && (
          <th className='px-3 py-2 text-left font-medium'>算法</th>
        )}
        {col('tags') && (
          <th className='px-3 py-2 text-left font-medium'>标签</th>
        )}
        {col('rounds') && (
          <th className='px-3 py-2 text-left font-medium'>轮次·时长</th>
        )}
        {col('updatedAt') && (
          <th className='px-3 py-2 text-left font-medium'>
            <SortableHeader label='更新时间' active />
          </th>
        )}
        {col('id') && (
          <th className='px-3 py-2 text-left font-medium'>ID</th>
        )}
        <th className='w-28 px-3 py-2 text-right font-medium'>操作</th>
      </tr>
    </thead>
  )
}
