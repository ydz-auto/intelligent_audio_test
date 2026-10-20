/**
 * 用例筛选工具栏（11_用例域.md §3.4 DataTableToolbar 形态）：
 * 搜索（debounce 500ms）+ 分组/标签/评估维度 facet chips + 全局算法联动 chip
 * + 收藏/回收站工具条（回收站态「全部恢复」ghost 钮）+ 重置。
 * 标签 facet 按分类分组呈现（INT-487：选项组头=分类名，数据源 GET /tags/by-category），
 * singleSelect + Command 搜索（INT-592 裁定由多选改单选——后端 tag 参数为单值）。
 * INT-486 用例不分类型口径（负责人 2026-10-16）：测试类型 facet 移除——用例无 api/e2e 之分。
 */
import { Check, ChevronDown, FilterX, Search, Tag } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import type { TagItem } from '@/domain/models/testTag'
import { DimensionSelect } from '@/features/algorithm-config/mutate/dimension-select'
import { FavoriteTrashToggle } from '@/features/testcases/components/favorite-trash-toggle'
import { TestCasesAlgorithmChip } from '@/features/testcases/components/global-algorithm-chip'

export interface TestCasesFilterToolbarProps {
  filters: TestCaseListFilters
  onChange: (next: TestCaseListFilters) => void
  onReset: () => void
  isFiltered: boolean
  groups: TestCaseGroup[]
  tags: TagItem[]
  /** 评估维度全量（含子维度；评估维度 facet 按 分组/主维度/子维度 单选，INT-1030 全站一致性） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories?: EvaluationCategory[]
  /** 已加载/已筛选用例集（INT-677：标签 facet 计数从该集实时聚合，与列表同源；回收站项不计入） */
  cases: TestCaseListItem[]
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

/**
 * 标签 facet（11_用例域.md §3.4/§3.6，INT-592 裁定单选）：
 * singleSelect + Command 搜索（输入过滤标签名）+ 选项按分类分组展示
 * （组头=分类名，数据源 GET /tags/by-category，INT-487 口径）+ 色点 +
 * 客户端聚合计数（§3.4：/tags/by-category 未返回 count，暂从已加载集聚合；
 * INT-677：聚合源改为父级传入的已加载/已筛选用例集，不再走 mock）。
 * 空态「暂无标签」；选中项再点 = 取消（清空标签筛选，与重置联动）。
 */
function TagFacet({
  value,
  tags,
  caseCounts,
  onChange,
}: {
  value: string | null
  tags: TagItem[]
  caseCounts: Record<string, number>
  onChange: (value: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  // Command 搜索过滤 + 按分类分组（未分类兜底）
  const grouped = useMemo(() => {
    const kw = query.trim().toLowerCase()
    const source = kw
      ? tags.filter(
          (t) =>
            t.name.toLowerCase().includes(kw) ||
            (t.categoryName ?? '').toLowerCase().includes(kw)
        )
      : tags
    const map = new Map<string, TagItem[]>()
    for (const tag of source) {
      const key = tag.categoryName ?? '未分类'
      map.set(key, [...(map.get(key) ?? []), tag])
    }
    return [...map.entries()].sort(([a], [b]) =>
      a === '未分类' ? 1 : b === '未分类' ? -1 : a.localeCompare(b, 'zh-CN')
    )
  }, [tags, query])

  const selectedTag = tags.find((t) => t.name === value)

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (!o) setQuery('')
      }}
    >
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
        {selectedTag ? (
          <span className='flex min-w-0 items-center gap-1.5'>
            <span
              aria-hidden='true'
              className='size-2 shrink-0 rounded-full'
              style={{ backgroundColor: selectedTag.color ?? '#94a3b8' }}
            />
            <span className='max-w-28 truncate font-medium'>
              {selectedTag.name}
            </span>
          </span>
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
            {/* Command 搜索（§3.4：FacetedFilter singleSelect 同款） */}
            <div className='relative mb-1'>
              <Search
                aria-hidden='true'
                className='text-muted-foreground absolute top-1/2 start-2 size-3.5 -translate-y-1/2'
              />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder='搜索标签...'
                aria-label='搜索标签'
                className='h-8 ps-7'
              />
            </div>
            <div className='border-border/60 mb-1 flex max-h-60 flex-col gap-1 overflow-y-auto'>
              {grouped.length === 0 ? (
                <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
                  没有找到匹配的标签
                </p>
              ) : (
                grouped.map(([categoryName, items]) => (
                  <div key={categoryName}>
                    <p className='text-muted-foreground px-2 pt-1 pb-0.5 text-xs font-medium'>
                      {categoryName}
                    </p>
                    {items.map((tag) => {
                      const checked = value === tag.name
                      const count = caseCounts[tag.name] ?? 0
                      return (
                        <button
                          key={tag.id}
                          type='button'
                          onClick={() => {
                            onChange(checked ? null : tag.name)
                            setOpen(false)
                            setQuery('')
                          }}
                          className={cn(
                            'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                            checked && 'bg-accent'
                          )}
                        >
                          <span
                            aria-hidden='true'
                            className='size-2 shrink-0 rounded-full'
                            style={{ backgroundColor: tag.color ?? '#94a3b8' }}
                          />
                          <span className='min-w-0 flex-1 truncate'>
                            {tag.name}
                          </span>
                          {count > 0 && (
                            <span
                              aria-hidden='true'
                              className='text-muted-foreground shrink-0 text-xs tabular-nums'
                            >
                              {count}
                            </span>
                          )}
                          {checked && (
                            <Check
                              aria-hidden='true'
                              className='size-4 shrink-0'
                            />
                          )}
                        </button>
                      )
                    })}
                  </div>
                ))
              )}
            </div>
            {value != null && (
              <div className='border-t pt-1'>
                <button
                  type='button'
                  className='text-muted-foreground hover:text-foreground text-xs font-medium transition-colors'
                  onClick={() => {
                    onChange(null)
                    setOpen(false)
                    setQuery('')
                  }}
                >
                  清空选择
                </button>
              </div>
            )}
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

const fallbackTag = (name: string): TagItem => ({
  id: -1,
  name,
  description: null,
  color: null,
  categoryId: null,
  categoryName: null,
  createdAt: null,
  updatedAt: null,
})

/**
 * 标签操作 DropdownMenu（11_用例域.md §3.6 收编①：标签 facet 单选选中态后工具栏右端出现）。
 * 三项操作逐钮按权限过滤：编辑标签（tag:update → §5.4）/ 删除标签（tag:delete，级联确认
 * destructive）/ 复制标签下用例（testcase:copy）；批量已单轨收勾选浮条（§3.7），下拉不挂批量。
 * 一等管理位=标签管理页（§4.2，对齐 INT-417 口径）。
 * 权限口径（§7 注 1）：写权限逐钮禁用+Tooltip，不整组隐藏——只读角色
 * （algo_engineer 等）无标签写能力时下拉保留、三项逐钮置灰（无 hook 早退）。
 */
function TagActionsDropdown({
  tagName,
  tags,
  caseCounts,
}: {
  tagName: string
  tags: TagItem[]
  caseCounts: Record<string, number>
}) {
  const { hasPermission } = usePermissions()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState<{
    kind: 'delete' | 'copy'
    tag: TagItem
    count: number
  } | null>(null)

  const canEdit = hasPermission('tag:update')
  const canDelete = hasPermission('tag:delete')
  const canCopy = hasPermission('testcase:copy')
  // §7 注 1：不整组隐藏——写权限逐钮禁用 + Tooltip（hook 调用保持无条件）
  const registry = useMemo(() => new Map(tags.map((t) => [t.name, t])), [tags])
  const tag = registry.get(tagName) ?? fallbackTag(tagName)
  const count = caseCounts[tag.name] ?? 0

  const disabledItem = (reason: string, label: string) => (
    <DropdownMenuItem disabled title={reason}>
      {label}
    </DropdownMenuItem>
  )

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger
          render={
            <Button
              variant='outline'
              size='sm'
              className='h-8 gap-1.5 px-2.5 font-normal'
            />
          }
        >
          <Tag aria-hidden='true' className='size-3.5' />
          <span className='text-muted-foreground'>标签操作</span>
          <ChevronDown
            aria-hidden='true'
            className={cn('size-3.5 transition-transform', open && 'rotate-180')}
          />
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-44'>
          <DropdownMenuGroup>
            <DropdownMenuLabel className='truncate'>
              标签「{tag.name}」
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          {canEdit ? (
            <DropdownMenuItem
              onSelect={() => {
                setOpen(false)
                toast.success(`编辑标签「${tag.name}」（演示）`)
              }}
            >
              编辑标签
            </DropdownMenuItem>
          ) : (
            disabledItem('无 tag:update 权限', '编辑标签')
          )}
          {canDelete ? (
            <DropdownMenuItem
              variant='destructive'
              onSelect={() => {
                setOpen(false)
                setConfirm({ kind: 'delete', tag, count })
              }}
            >
              删除标签
            </DropdownMenuItem>
          ) : (
            disabledItem('无 tag:delete 权限', '删除标签')
          )}
          {canCopy ? (
            <DropdownMenuItem
              onSelect={() => {
                setOpen(false)
                setConfirm({ kind: 'copy', tag, count })
              }}
            >
              复制标签下用例
            </DropdownMenuItem>
          ) : (
            disabledItem('无 testcase:copy 权限', '复制标签下用例')
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirm != null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.kind === 'delete' ? '删除标签' : '复制标签下用例'}
        desc={
          confirm?.kind === 'delete'
            ? `确定要删除标签「${confirm.tag.name}」吗？该操作将级联删除标签下的 ${confirm.count} 个用例，不可恢复！`
            : `确定要复制标签「${confirm?.tag.name ?? ''}」下的 ${confirm?.count ?? 0} 个用例吗？复制后将生成新标签：${confirm?.tag.name ?? ''}_copy`
        }
        confirmText={confirm?.kind === 'delete' ? '删除' : '复制'}
        destructive={confirm?.kind === 'delete'}
        handleConfirm={() => {
          if (!confirm) return
          if (confirm.kind === 'delete') {
            toast.success('标签已删除', {
              description: `已级联删除 ${confirm.count} 个用例`,
            })
          } else {
            toast.success('已复制标签下用例', {
              description: `新标签：${confirm.tag.name}_copy`,
            })
          }
          setConfirm(null)
        }}
      >
        {confirm?.kind === 'copy' && (
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox defaultChecked />
            同时复制到新分组
          </label>
        )}
      </ConfirmDialog>
    </>
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
  categories = [],
  cases,
  onRestoreAll,
}: TestCasesFilterToolbarProps) {
  const searchRef = useRef<HTMLInputElement>(null)
  const [searchInput, setSearchInput] = useState(filters.search ?? '')

  /**
   * 标签下在用（未删除）用例数（INT-677：客户端从已加载/已筛选用例集实时聚合，
   * §3.4 计数与列表同源；§3.6 删除/复制级联计数；回收站项不计入——级联作用于在用集）
   */
  const tagCaseCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of cases) {
      if (c.deleted) continue
      for (const t of c.tags) m.set(t, (m.get(t) ?? 0) + 1)
    }
    return Object.fromEntries(m)
  }, [cases])

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
  /** 评估维度 facet 当前选中（按 id 精确匹配；维度可能不在候选集时回退原值） */
  const currentDimension =
    filters.dimensionId != null
      ? dimensions.find((d) => String(d.id) === String(filters.dimensionId)) ?? null
      : null

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
          label='分组'
          value={filters.groupId ?? null}
          options={groupOptions}
          onChange={(v) => update({ groupId: v ?? null })}
        />
        <TagFacet
          value={filters.tag ?? null}
          tags={tags}
          caseCounts={tagCaseCounts}
          onChange={(tag) => update({ tag })}
        />
        {/* 评估维度 facet（INT-1030：按 分组→主维度→子维度 单选，全站一致性；「全部」清除） */}
        <DimensionSelect
          dimensions={dimensions}
          categories={categories}
          value={currentDimension ? String(currentDimension.id) : ''}
          onValueChange={(v) => update({ dimensionId: v === '' ? null : Number(v) })}
          valueOf={(d) => String(d.id)}
          placeholder='全部'
          clearLabel='全部'
          triggerLabel='评估维度'
          ariaLabel='评估维度筛选'
          triggerClassName='h-8 gap-1.5 rounded-lg px-2.5 font-normal'
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

        {/* §3.6 收编①：标签 facet 单选选中态后工具栏右端出现标签操作入口 */}
        {!isTrash && filters.tag != null && (
          <TagActionsDropdown
            tagName={filters.tag}
            tags={tags}
            caseCounts={tagCaseCounts}
          />
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
