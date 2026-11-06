/**
 * 评估维度三级树（15_报告域.md §3.3.7 / §3.5.10，INT-1738）。
 *
 * 形态照 11_用例域 §5.1.3.1「维度 chips 主/子分组云 + 分类分组」：
 * **分类组头（分类名 + `{已选}/{总数}`）→ 主维度行（「主」徽章 + 子维度数角标）→ 子维度行（缩进 + 「子」徽章）**。
 * - 勾主维度联动全部子维度（父项 indeterminate 时可单独取消子项）；
 * - 搜索命中子维度时带出父维度上下文，命中主维度整组展示；
 * - 孤儿子维度（父维度不在本报告）挂「未分类」组末尾，照常可勾选。
 * 一处实现多点复用：显示设置「评估维度」Section、§3.3.7 筛选卡评估维度多选、排序维度 Select 分组口径。
 */
import { Folder, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import type { DimensionTreeSection } from '@/application/report-view/use-report-filter-taxonomy'
import { UNCATEGORIZED_SECTION_KEY } from '@/application/report-view/use-report-filter-taxonomy'
import { cn } from '@/lib/utils'

export interface FilterDimensionTreeProps {
  sections: DimensionTreeSection[]
  /** 已选维度名（基础维度） */
  selected: string[]
  /** 勾选回调：names = 主维度 + 其子维度，或单个子维度 */
  onToggle: (names: string[], checked: boolean) => void
  showSearch?: boolean
  /** 每页主维度组数（缺省不分页；筛选卡传 8） */
  pageSize?: number
  /** 「全选 / 清空」小字按钮 */
  showBulkActions?: boolean
  /** 全部可选项（全选 / 清空用；缺省从 sections 推导） */
  allOptions?: string[]
  /** 置灰只读（当维由视图决定时用，§3.3.7 口径 A）——此处仅维度置灰兜底 */
  disabled?: boolean
  className?: string
}

interface FlatGroup {
  sectionKey: string
  sectionName: string
  main: string
  subs: string[]
  /** 搜索命中子维度时只展示命中的子维度 */
  visibleSubs: string[]
}

/** 搜索过滤：主维度命中 → 整组；子维度命中 → 父维度上下文 + 命中子维度 */
function filterGroups(sections: DimensionTreeSection[], keyword: string): FlatGroup[] {
  const kw = keyword.trim().toLowerCase()
  const out: FlatGroup[] = []
  for (const section of sections) {
    for (const group of section.groups) {
      const mainHit = !kw || group.main.toLowerCase().includes(kw)
      const hitSubs = group.subs.filter((s) => s.toLowerCase().includes(kw))
      if (!mainHit && hitSubs.length === 0) continue
      out.push({
        sectionKey: section.key,
        sectionName: section.name,
        main: group.main,
        subs: group.subs,
        visibleSubs: mainHit ? group.subs : hitSubs,
      })
    }
  }
  return out
}

export function FilterDimensionTree({
  sections,
  selected,
  onToggle,
  showSearch = true,
  pageSize,
  showBulkActions = false,
  allOptions,
  disabled = false,
  className,
}: FilterDimensionTreeProps) {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)

  const groups = useMemo(() => filterGroups(sections, keyword), [sections, keyword])
  const pages = pageSize ? Math.max(1, Math.ceil(groups.length / pageSize)) : 1
  useEffect(() => {
    setPage(1)
  }, [keyword])
  const visible = pageSize ? groups.slice((page - 1) * pageSize, page * pageSize) : groups

  const options = useMemo(
    () =>
      allOptions ??
      sections.reduce<string[]>((acc, section) => {
        for (const group of section.groups) acc.push(group.main, ...group.subs)
        return acc
      }, []),
    [allOptions, sections]
  )
  const selectedSet = new Set(selected)
  /** 分类组头计数「{已选}/{总数}」 */
  const sectionCounts = useMemo(() => {
    const map = new Map<string, { picked: number; total: number }>()
    for (const section of sections) {
      const names = section.groups.flatMap((g) => [g.main, ...g.subs])
      map.set(section.key, {
        picked: names.filter((n) => selectedSet.has(n)).length,
        total: names.length,
      })
    }
    return map
  }, [sections, selected])

  const selectAll = (checked: boolean) => {
    const targets = options.filter((name) => checked !== selectedSet.has(name))
    if (targets.length > 0) onToggle(targets, checked)
  }

  // 搜索命中主维度时展示全部子维度，计数按可见组算（组头 {已选}/{总数}）
  return (
    <div className={cn('space-y-2', className)}>
      {(showSearch || showBulkActions) && (
        <div className='flex items-center gap-2'>
          {showSearch && (
            <div className='relative min-w-0 flex-1'>
              <Search
                aria-hidden='true'
                className='text-muted-foreground absolute start-2 top-1/2 size-3 -translate-y-1/2'
              />
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder='搜索评估维度'
                aria-label='搜索评估维度'
                className='h-7 ps-6 text-xs'
              />
            </div>
          )}
          {showBulkActions && (
            <div className='flex shrink-0 items-center gap-1'>
              <Button
                variant='ghost'
                size='sm'
                className='text-muted-foreground h-6 px-1.5 text-xs'
                disabled={disabled}
                onClick={() => selectAll(true)}
              >
                全选
              </Button>
              <Button
                variant='ghost'
                size='sm'
                className='text-muted-foreground h-6 px-1.5 text-xs'
                disabled={disabled}
                onClick={() => selectAll(false)}
              >
                清空
              </Button>
            </div>
          )}
          <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
            已选 {selected.length}
          </span>
        </div>
      )}

      {visible.length === 0 ? (
        <p className='text-muted-foreground py-2 text-center text-xs'>没有匹配的评估维度</p>
      ) : (
        <div className='space-y-2'>
          {visible.map((group, index) => {
            const selectedSubs = group.visibleSubs.filter((s) => selectedSet.has(s))
            const mainChecked = selectedSet.has(group.main)
            const total = group.visibleSubs.length + 1
            const picked = selectedSubs.length + (mainChecked ? 1 : 0)
            const indeterminate =
              !mainChecked && selectedSubs.length > 0 && selectedSubs.length < group.visibleSubs.length
            const showHeader =
              index === 0 ||
              visible[index - 1].sectionKey !== group.sectionKey
            return (
              <div key={`${group.sectionKey}:${group.main}`} className='space-y-1'>
                {showHeader && (
                  <div
                    className={cn(
                      'text-muted-foreground flex items-center gap-1.5 px-0.5 text-xs font-medium',
                      group.sectionKey === UNCATEGORIZED_SECTION_KEY && 'opacity-80'
                    )}
                  >
                    <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                    <span className='truncate'>{group.sectionName}</span>
                    <span className='bg-muted shrink-0 rounded-full px-1.5 text-[10px] tabular-nums'>
                      {(() => {
                        const counts = sectionCounts.get(group.sectionKey)
                        return counts ? `${counts.picked}/${counts.total}` : `${picked}/${total}`
                      })()}
                    </span>
                  </div>
                )}
                <div className='flex flex-wrap items-center gap-1.5 ps-1'>
                  <label className='flex items-center gap-1.5 text-xs'>
                    <Checkbox
                      checked={mainChecked}
                      indeterminate={indeterminate}
                      disabled={disabled}
                      onCheckedChange={(checked) =>
                        onToggle([group.main, ...group.subs], checked === true)
                      }
                    />
                    <span className='font-medium'>{group.main}</span>
                    <Badge variant='outline' className='px-1 py-0 text-[10px] font-normal'>
                      主
                    </Badge>
                    {group.subs.length > 0 && (
                      <span className='bg-primary/15 text-primary inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold tabular-nums'>
                        {group.subs.length}
                      </span>
                    )}
                  </label>
                </div>
                {group.visibleSubs.length > 0 && (
                  <div className='flex flex-wrap items-center gap-x-3 gap-y-1 ps-6'>
                    {group.visibleSubs.map((sub) => (
                      <label key={sub} className='flex items-center gap-1.5 text-xs'>
                        <Checkbox
                          checked={selectedSet.has(sub)}
                          disabled={disabled}
                          onCheckedChange={(checked) => onToggle([sub], checked === true)}
                        />
                        <span className='text-muted-foreground font-mono text-[10px]'>└</span>
                        <span>{sub}</span>
                        <Badge variant='secondary' className='px-1 py-0 text-[10px] font-normal'>
                          子
                        </Badge>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {pages > 1 && (
        <div className='flex items-center justify-between text-xs'>
          <span className='text-muted-foreground tabular-nums'>
            第 {page} / {pages} 页
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
