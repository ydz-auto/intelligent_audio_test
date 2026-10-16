/**
 * 用例筛选工具栏（11_用例域.md §3.4 DataTableToolbar 形态）：
 * 搜索（debounce 500ms）+ 测试类型/分组/标签/评估维度 facet chips + 全局算法联动 chip
 * + 收藏/回收站工具条（回收站态「全部恢复」ghost 钮）+ 重置。
 * 标签 facet 按分类分组呈现（INT-487：选项组头=分类名，数据源 GET /tags/by-category）。
 */
import { Check, ChevronDown, FilterX, Search } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'
import type { TagItem } from '@/domain/models/testTag'
import {
  TEST_TYPE_OPTIONS,
} from '@/features/testcases/constants'
import { FavoriteTrashToggle } from '@/features/testcases/components/favorite-trash-toggle'
import { TestCasesAlgorithmChip } from '@/features/testcases/components/global-algorithm-chip'

export interface TestCasesFilterToolbarProps {
  filters: TestCaseListFilters
  onChange: (next: TestCaseListFilters) => void
  onReset: () => void
  isFiltered: boolean
  groups: TestCaseGroup[]
  tags: TagItem[]
  dimensions: EvaluationDimensionItem[]
  /** 回收站「全部恢复」 */
  onRestoreAll: () => void
}

/** 单选 facet chip（Popover + 选项列表 + 选中态） */
function SingleFacet({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string | null | undefined
  options: Array<{ value: string; label: string; dotColor?: string }>
  onChange: (value: string | null) => void
}) {
  const current = options.find((o) => o.value === value)
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-8 gap-1.5 px-2.5 font-normal'
          />
        }
      >
        <span className='text-muted-foreground'>{label}</span>
        <span className='max-w-28 truncate font-medium'>
          {current?.label ?? '全部'}
        </span>
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='min-w-48 p-1.5'>
        {options.map((option) => (
          <button
            key={option.value}
            type='button'
            onClick={() => {
              onChange(option.value === value ? null : option.value)
              setOpen(false)
            }}
            className={cn(
              'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
              option.value === value && 'bg-accent'
            )}
          >
            {option.dotColor && (
              <span
                aria-hidden='true'
                className='size-2 shrink-0 rounded-full'
                style={{ backgroundColor: option.dotColor }}
              />
            )}
            <span className='min-w-0 flex-1 truncate'>{option.label}</span>
            {option.value === value && (
              <Check aria-hidden='true' className='size-4 shrink-0' />
            )}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

/** 标签 facet（INT-487 按分类分组：选项组头=分类名 + 色点；多选 + 计数） */
function TagFacet({
  value,
  tags,
  onChange,
}: {
  value: string[]
  tags: TagItem[]
  onChange: (value: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const activeCount = value.length

  // 按分类分组（未分类兜底）
  const grouped = useCallback(() => {
    const map = new Map<string, TagItem[]>()
    for (const tag of tags) {
      const key = tag.categoryName ?? '未分类'
      map.set(key, [...(map.get(key) ?? []), tag])
    }
    return [...map.entries()].sort(([a], [b]) => (a === '未分类' ? 1 : b === '未分类' ? -1 : a.localeCompare(b, 'zh-CN')))
  }, [tags])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-8 gap-1.5 px-2.5 font-normal'
          />
        }
      >
        <span className='text-muted-foreground'>标签</span>
        {activeCount > 0 ? (
          <Badge className='rounded-sm px-1 font-normal'>{activeCount}</Badge>
        ) : (
          <span className='max-w-28 truncate font-medium'>全部</span>
        )}
        <ChevronDown
          aria-hidden='true'
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </PopoverTrigger>
      <PopoverContent align='start' className='max-w-72 min-w-56 p-1.5'>
        {tags.length === 0 ? (
          <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
            暂无标签
          </p>
        ) : (
          <>
            <div className='border-border/60 mb-1 flex max-h-60 flex-col gap-1 overflow-y-auto'>
              {grouped().map(([categoryName, items]) => (
                <div key={categoryName}>
                  <p className='text-muted-foreground px-2 pt-1 pb-0.5 text-xs font-medium'>
                    {categoryName}
                  </p>
                  {items.map((tag) => {
                    const checked = value.includes(tag.name)
                    return (
                      <label
                        key={tag.id}
                        className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors'
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() =>
                            onChange(
                              checked
                                ? value.filter((v) => v !== tag.name)
                                : [...value, tag.name]
                            )
                          }
                        />
                        <span
                          aria-hidden='true'
                          className='size-2 shrink-0 rounded-full'
                          style={{ backgroundColor: tag.color ?? '#94a3b8' }}
                        />
                        <span className='min-w-0 flex-1 truncate'>
                          {tag.name}
                        </span>
                      </label>
                    )
                  })}
                </div>
              ))}
            </div>
            <div className='border-t pt-1'>
              <button
                type='button'
                className='text-muted-foreground hover:text-foreground text-xs font-medium transition-colors'
                onClick={() => onChange([])}
              >
                清空选择
              </button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

export function TestCasesFilterToolbar({
  filters,
  onChange,
  onReset,
  isFiltered,
  groups,
  tags,
  dimensions,
  onRestoreAll,
}: TestCasesFilterToolbarProps) {
  const searchRef = useRef<HTMLInputElement>(null)
  const [searchInput, setSearchInput] = useState(filters.search ?? '')

  const update = useCallback(
    (patch: Partial<TestCaseListFilters>) => onChange({ ...filters, ...patch }),
    [filters, onChange]
  )

  /** 搜索 debounce 500ms（users 表同款） */
  const debounceTimer = useRef<number | null>(null)
  const handleSearchChange = (value: string) => {
    setSearchInput(value)
    if (debounceTimer.current) window.clearTimeout(debounceTimer.current)
    debounceTimer.current = window.setTimeout(() => {
      update({ search: value.trim() })
    }, 500)
  }

  const isTrash = filters.trash === true
  const groupOptions = [
    ...groups.map((g) => ({ value: g.id, label: g.name })),
    { value: '__ungrouped__', label: '未分组' },
  ]
  const dimensionOptions = dimensions.map((d) => ({
    value: String(d.id),
    label: d.name,
  }))

  return (
    <div className='bg-card/50 rounded-lg border p-2.5 sm:p-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
          />
          <Input
            ref={searchRef}
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder='搜索用例名称或描述'
            className='h-8 w-full sm:w-[200px] lg:w-[240px] ps-7'
            aria-label='搜索用例'
          />
        </div>

        <SingleFacet
          label='测试类型'
          value={filters.type ?? null}
          options={[...TEST_TYPE_OPTIONS]}
          onChange={(v) => update({ type: v })}
        />
        <SingleFacet
          label='分组'
          value={filters.groupId ?? null}
          options={groupOptions}
          onChange={(v) => update({ groupId: v ?? null })}
        />
        <TagFacet
          value={filters.tags ?? []}
          tags={tags}
          onChange={(tagNames) => update({ tags: tagNames })}
        />
        <SingleFacet
          label='评估维度'
          value={filters.dimensionId != null ? String(filters.dimensionId) : null}
          options={dimensionOptions}
          onChange={(v) => update({ dimensionId: v ? Number(v) : null })}
        />

        <TestCasesAlgorithmChip />
        <FavoriteTrashToggle
          value={{
            favorite: filters.favorite ?? false,
            trash: filters.trash ?? false,
          }}
          onChange={(v) => update({ favorite: v.favorite, trash: v.trash })}
        />
        {isTrash && (
          <Button
            variant='ghost'
            size='sm'
            className='h-8 gap-1 px-2.5'
            onClick={onRestoreAll}
          >
            全部恢复
          </Button>
        )}

        {isFiltered && (
          <Button
            variant='ghost'
            size='sm'
            className='h-8 gap-1 px-2.5'
            onClick={onReset}
          >
            <FilterX aria-hidden='true' className='size-3.5' />
            重置
          </Button>
        )}
      </div>
    </div>
  )
}
