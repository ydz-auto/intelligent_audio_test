/**
 * 用例标签两级树（15_报告域.md §3.3.7，INT-1738）。
 *
 * 「标签筛选也是照着分类 标签 俩级显示」——分类组头（分类名 + 组内计数，标签带色点）→ 标签行；
 * 「未分类」固定尾组弱化。分类来源见 `useReportFilterTaxonomy`（快照 → by-category 兜底 → 未分类）。
 * 分页整节同页：「未分类」尾组不跨页截断（单节超过 pageSize 时仍跨页，INT-2101）。
 * **筛选请求不变**：仍只传标签名数组，分类仅影响展示。
 */
import { Folder, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import type { TagTreeSection } from '@/application/report-view/use-report-filter-taxonomy'
import { UNCATEGORIZED_SECTION_KEY } from '@/application/report-view/use-report-filter-taxonomy'
import { cn } from '@/lib/utils'

export interface FilterTagTreeProps {
  sections: TagTreeSection[]
  selected: string[]
  onToggle: (name: string, checked: boolean) => void
  showSearch?: boolean
  /** 每页标签数（缺省不分页；筛选卡传 8） */
  pageSize?: number
  /** 标签色点（标签名 → 色值；报告快照无色值时省略） */
  colorOf?: (name: string) => string | null | undefined
  className?: string
}

interface FlatTag {
  sectionKey: string
  sectionName: string
  name: string
}

/**
 * 分页：整节不跨页——「未分类」尾组保证可见（分页不截断，INT-2101）。
 * 一节整体放得进下一页时才翻页（单节 > pageSize 时自然跨页）；搜索过滤后的稀疏节同样整节保留。
 */
export function paginateSections(flat: FlatTag[], pageSize: number): FlatTag[][] {
  if (pageSize <= 0) return [flat]
  const pages: FlatTag[][] = []
  let current: FlatTag[] = []
  let i = 0
  while (i < flat.length) {
    const sectionKey = flat[i].sectionKey
    let sectionEnd = i
    while (sectionEnd < flat.length && flat[sectionEnd].sectionKey === sectionKey) {
      sectionEnd += 1
    }
    const sectionSize = sectionEnd - i
    const remaining = pageSize - current.length
    // 本节放不下当前页剩余位、但整节能放进新一页 → 先翻页，避免节跨页
    if (current.length > 0 && sectionSize > remaining && sectionSize <= pageSize) {
      pages.push(current)
      current = []
    }
    while (i < sectionEnd) {
      current.push(flat[i])
      i += 1
      if (current.length === pageSize) {
        pages.push(current)
        current = []
      }
    }
  }
  if (current.length > 0) pages.push(current)
  return pages
}

export function FilterTagTree({
  sections,
  selected,
  onToggle,
  showSearch = true,
  pageSize,
  colorOf,
  className,
}: FilterTagTreeProps) {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)

  const flat = useMemo<FlatTag[]>(() => {
    const kw = keyword.trim().toLowerCase()
    const out: FlatTag[] = []
    for (const section of sections) {
      for (const name of section.tags) {
        if (kw && !name.toLowerCase().includes(kw)) continue
        out.push({ sectionKey: section.key, sectionName: section.name, name })
      }
    }
    return out
  }, [sections, keyword])

  const paginated = useMemo(
    () => (pageSize ? paginateSections(flat, pageSize) : [flat]),
    [flat, pageSize]
  )
  useEffect(() => {
    setPage(1)
  }, [keyword, sections])
  const visible = pageSize ? paginated[page - 1] ?? [] : flat
  const selectedSet = new Set(selected)
  const counts = useMemo(() => {
    const map = new Map<string, { picked: number; total: number }>()
    for (const section of sections) {
      map.set(section.key, {
        picked: section.tags.filter((t) => selectedSet.has(t)).length,
        total: section.tags.length,
      })
    }
    return map
  }, [sections, selected])

  return (
    <div className={cn('space-y-2', className)}>
      {showSearch && (
        <div className='flex items-center gap-2'>
          <div className='relative min-w-0 flex-1'>
            <Search
              aria-hidden='true'
              className='text-muted-foreground absolute start-2 top-1/2 size-3 -translate-y-1/2'
            />
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder='搜索用例标签'
              aria-label='搜索用例标签'
              className='h-7 ps-6 text-xs'
            />
          </div>
          <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
            已选 {selected.length}
          </span>
        </div>
      )}

      {visible.length === 0 ? (
        <p className='text-muted-foreground py-2 text-center text-xs'>无匹配标签</p>
      ) : (
        <div className='space-y-1.5'>
          {visible.map((tag, index) => {
            const showHeader = index === 0 || visible[index - 1].sectionKey !== tag.sectionKey
            const count = counts.get(tag.sectionKey)
            const color = colorOf?.(tag.name)
            return (
              <div key={`${tag.sectionKey}:${tag.name}`} className='space-y-1'>
                {showHeader && (
                  <div
                    className={cn(
                      'text-muted-foreground flex items-center gap-1.5 px-0.5 text-xs font-medium',
                      tag.sectionKey === UNCATEGORIZED_SECTION_KEY && 'opacity-80'
                    )}
                  >
                    <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                    <span className='truncate'>{tag.sectionName}</span>
                    {count && (
                      <span className='bg-muted shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
                        {count.picked}/{count.total}
                      </span>
                    )}
                  </div>
                )}
                <label className='flex items-center gap-1.5 ps-5 text-xs'>
                  <Checkbox
                    checked={selectedSet.has(tag.name)}
                    onCheckedChange={(checked) => onToggle(tag.name, checked === true)}
                  />
                  {color && (
                    <span
                      aria-hidden='true'
                      className='size-1.5 shrink-0 rounded-full'
                      style={{ backgroundColor: color }}
                    />
                  )}
                  <span className='truncate'>{tag.name}</span>
                </label>
              </div>
            )
          })}
        </div>
      )}

      {paginated.length > 1 && (
        <div className='flex items-center justify-between text-xs'>
          <span className='text-muted-foreground tabular-nums'>
            第 {page} / {paginated.length} 页
          </span>
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
              disabled={page >= paginated.length}
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
