/**
 * 用例筛选工具栏（11_用例域.md §3.4 DataTableToolbar 形态）：
 * 搜索（debounce 500ms）+ 分组/标签/评估维度 facet chips + 全局算法联动 chip
 * + 收藏/回收站工具条（回收站态「全部恢复」ghost 钮）+ 重置。
 * 标签 facet 按分类分组呈现（INT-487：选项组头=分类名，数据源 GET /tags/by-category）。
 * INT-486 用例不分类型口径（负责人 2026-10-16）：测试类型 facet 移除——用例无 api/e2e 之分。
 */
import { Check, ChevronDown, FilterX, Search, Tag } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
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
import { MOCK_TEST_CASES } from '@/infrastructure/mock/testcases-mock'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { EvaluationDimensionItem } from '@/domain/models/evaluationDimension'
import type { TagItem } from '@/domain/models/testTag'
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

/** 标签下用例数（mock 源派生；删除/复制级联计数口径 §3.6，接线后随列表查询） */
const TAG_CASE_COUNTS: Record<string, number> = (() => {
  const m = new Map<string, number>()
  for (const c of MOCK_TEST_CASES) {
    for (const t of c.tags) m.set(t, (m.get(t) ?? 0) + 1)
  }
  return Object.fromEntries(m)
})()

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
 * 标签操作 DropdownMenu（11_用例域.md §3.6 收编①：标签 facet 选中态后工具栏右端出现）。
 * 入口：编辑标签 / 删除标签（级联删除用例，destructive）/ 复制标签下用例；
 * 另一入口=标签管理页（§4.2）。批量已单轨收勾选浮条（§3.7.1，组头/标签下拉不再挂批量）。
 * 多标签选中态下编辑/删除语义二义 → 禁用 + Tooltip（INT-592 改单选后为防御性保留）。
 * 权限口径（§7 注 1）：写权限禁用+Tooltip；缺全部写权限时整组隐藏。
 */
function TagActionsDropdown({
  tagNames,
  tags,
}: {
  tagNames: string[]
  tags: TagItem[]
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
  // §7 注 1：读权限隐藏——只读角色（algo_engineer 等）无标签写能力时整组不出现
  if (!canEdit && !canDelete && !canCopy) return null

  const registry = useMemo(() => new Map(tags.map((t) => [t.name, t])), [tags])
  const primary = registry.get(tagNames[0]) ?? fallbackTag(tagNames[0])
  const multi = tagNames.length > 1
  const count = TAG_CASE_COUNTS[primary.name] ?? 0
  const singleTooltip = multi ? '请先单选一个标签' : undefined

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
              标签「{primary.name}」
              {multi && ` 等 ${tagNames.length} 个`}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          {canEdit ? (
            <DropdownMenuItem
              disabled={multi}
              title={singleTooltip}
              onSelect={() => {
                setOpen(false)
                toast.success(`编辑标签「${primary.name}」（演示）`)
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
              disabled={multi}
              title={singleTooltip}
              onSelect={() => {
                setOpen(false)
                setConfirm({ kind: 'delete', tag: primary, count })
              }}
            >
              删除标签
            </DropdownMenuItem>
          ) : (
            disabledItem('无 tag:delete 权限', '删除标签')
          )}
          {canCopy ? (
            <DropdownMenuItem
              disabled={multi}
              title={singleTooltip}
              onSelect={() => {
                setOpen(false)
                setConfirm({ kind: 'copy', tag: primary, count })
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

        {/* §3.6 收编①：标签 facet 选中态后工具栏右端出现标签操作入口 */}
        {!isTrash && (filters.tags?.length ?? 0) > 0 && (
          <TagActionsDropdown tagNames={filters.tags ?? []} tags={tags} />
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
