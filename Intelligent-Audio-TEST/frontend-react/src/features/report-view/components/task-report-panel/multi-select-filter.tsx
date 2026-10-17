/**
 * 多选筛选组（15_报告域.md §3.3.7/3.3.8，FilterComponent 报告域定制消费）。
 * 分组/标签/评估维度多选 = 关键词搜索 + 每页 8 个翻页（原实现全铺 chip/checkbox 无界）；
 * 「已选条件 (N)」逐项可删（§3.3.8 底部条件条）。
 */
import { Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface MultiSelectFilterProps {
  /** 组名（如「用例分组」「用例标签」「评估维度」） */
  label: string
  options: string[]
  selected: string[]
  onToggle: (value: string) => void
  /** 选项展示名映射（分组重命名场景；缺省用原值） */
  display?: (value: string) => string
  /** 每页选项数（默认 8） */
  pageSize?: number
  /** checkbox 形态（分组/标签对比用）；缺省 chip 形态（具体用例用） */
  variant?: 'chip' | 'checkbox'
}

export function MultiSelectFilter({
  label,
  options,
  selected,
  onToggle,
  display,
  pageSize = 8,
  variant = 'chip',
}: MultiSelectFilterProps) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)

  const filtered = useMemo(
    () => options.filter((o) => o.toLowerCase().includes(query.trim().toLowerCase())),
    [options, query]
  )
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  // 关键词变化重置翻页（当前页可能越界）
  useEffect(() => {
    setPage(1)
  }, [query])
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize)

  return (
    <div className='flex flex-col gap-1.5'>
      <div className='flex items-center gap-2'>
        <span className='text-muted-foreground w-16 shrink-0 text-xs'>{label}</span>
        <div className='relative min-w-0 flex-1'>
          <Search aria-hidden='true' className='text-muted-foreground absolute start-2 top-1/2 size-3 -translate-y-1/2' />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`搜索${label}...`}
            className='h-7 max-w-52 ps-6 text-xs'
          />
        </div>
        <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
          已选 {selected.length}
        </span>
      </div>

      {visible.length === 0 ? (
        <p className='text-muted-foreground ps-16 text-xs'>无匹配选项</p>
      ) : variant === 'checkbox' ? (
        <div className='flex flex-wrap items-center gap-x-4 gap-y-1 ps-16'>
          {visible.map((o) => (
            <label key={o} className='flex items-center gap-1.5 text-xs'>
              <Checkbox
                checked={selected.includes(o)}
                onCheckedChange={() => onToggle(o)}
              />
              {display?.(o) ?? o}
            </label>
          ))}
        </div>
      ) : (
        <div className='flex flex-wrap gap-1.5 ps-16'>
          {visible.map((o) => {
            const active = selected.includes(o)
            return (
              <button
                key={o}
                type='button'
                aria-pressed={active}
                className={cn(
                  'rounded-md px-2 py-0.5 text-xs transition-colors',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                )}
                onClick={() => onToggle(o)}
              >
                {display?.(o) ?? o}
              </button>
            )
          })}
        </div>
      )}

      {pages > 1 && (
        <div className='flex items-center justify-between ps-16 text-xs'>
          <span className='text-muted-foreground tabular-nums'>第 {page} / {pages} 页</span>
          <div className='flex items-center gap-1'>
            <button
              type='button'
              className='hover:bg-muted text-muted-foreground rounded px-2 py-0.5 disabled:opacity-40'
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </button>
            <button
              type='button'
              className='hover:bg-muted text-muted-foreground rounded px-2 py-0.5 disabled:opacity-40'
              disabled={page >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** §3.3.8「已选条件 (N)」逐项可删（多组条件聚合展示；onRemove 按条件 key 分发） */
export function SelectedConditionsBar({
  conditions,
  onRemove,
}: {
  conditions: { key: string; label: string }[]
  onRemove: (key: string) => void
}) {
  if (conditions.length === 0) return null
  return (
    <div className='mt-2 flex flex-wrap items-center gap-1.5 border-t pt-2'>
      <span className='text-muted-foreground shrink-0 text-xs'>已选条件 ({conditions.length})</span>
      {conditions.map((c) => (
        <Badge key={c.key} variant='secondary' className='gap-1 pr-1 text-xs font-normal'>
          {c.label}
          <button
            type='button'
            aria-label={`移除条件 ${c.label}`}
            className='hover:bg-muted rounded-sm p-0.5 transition-colors'
            onClick={() => onRemove(c.key)}
          >
            <X aria-hidden='true' className='size-3' />
          </button>
        </Badge>
      ))}
    </div>
  )
}
