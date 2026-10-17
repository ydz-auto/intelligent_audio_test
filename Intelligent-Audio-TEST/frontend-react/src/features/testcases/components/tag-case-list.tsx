/**
 * 标签视图卡片流（V9.7.10 TestCaseListContainer.vue 标签视图等价移植，11_用例域.md §3.6）。
 * 标签分组卡：组头（勾选全选 + ChevronDown 展开/折叠 + 标签色点图标 + 标签名 + 计数 Badge）+
 * 组内用例卡（CaseCard）；标签级懒加载分页（每页 5 个标签 +「已显示 {n} / {总} 个标签 · 加载更多」）。
 * 数据契约：后端 view=tag 返回 {items:[{tag,testCases}]}，mock 阶段由平铺 cases 按 tag 聚合派生
 * （同一用例命中多个标签时多卡呈现，对齐 V9.7.10 tagViewData Record<tagName, cases>）。
 * INT-487 按分类呈现：标签色点/角标走 TagItem.color/categoryName 数据驱动色。
 */
import { ArrowUpDown, ChevronDown, FolderOpen, Tags } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useIsFetching } from '@tanstack/react-query'

import { useSessionMap } from '@/application/testcases/use-session-map'
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
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { groupCasesByCaseGroup } from '@/domain/lib/sub-view-aggregation'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'
import { CaseCard, type CaseCardCallbacks } from '@/features/testcases/components/case-card'
import {
  CaseSubViewToggle,
  TAG_SUB_VIEW_OPTIONS,
} from '@/features/testcases/components/case-sub-view-toggle'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'

/** 标签分页每页数（V9.7.10 itemsPerPage=5 语义平移） */
const TAG_LIST_PAGE = 5

type TagSortKey = 'count' | 'name'

/** 标签分组（标签名 → 用例列表） */
interface TagGroup {
  name: string
  cases: TestCaseListItem[]
  color: string | null
  categoryName: string | null
}

export function TagCaseList({
  cases,
  loading,
  selected,
  tagRegistry,
  callbacks,
  onToggleSelect,
  onToggleAll,
  onCreate,
}: {
  cases: TestCaseListItem[]
  loading: boolean
  selected: Set<string>
  tagRegistry: TagItem[]
  callbacks: CaseCardCallbacks
  onToggleSelect: (id: string, checked: boolean) => void
  onToggleAll: (ids: string[], checked: boolean) => void
  onCreate: () => void
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [tagPage, setTagPage] = useState(1)
  const [sortKey, setSortKey] = useState<TagSortKey>('count')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  /** 标签卡子视图（§3.6 会话内存 per-tag，缺省 flat） */
  const tagSubView = useSessionMap((s) => s.tagSubView)
  const setTagSubView = useSessionMap((s) => s.setTagSubView)
  /** §3.3.3：isFetching 时列表不消失、降透明度（placeholderData 保上一帧） */
  const fetching = useIsFetching({ queryKey: ['testcases'] })
  const dimmed = fetching > 0 && !loading

  // INT-490 P2 同源修复：标签卡默认全展开（标签分组由平铺用例聚合派生，加载后补齐）
  useEffect(() => {
    if (cases.length === 0) return
    const names = new Set(cases.flatMap((c) => c.tags))
    setExpanded((prev) => {
      const next = new Set(prev)
      let changed = false
      for (const name of names) {
        if (!next.has(name)) {
          next.add(name)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [cases])

  const registry = useMemo(() => {
    const map = new Map<string, TagItem>()
    for (const t of tagRegistry) map.set(t.name, t)
    return map
  }, [tagRegistry])

  const tagGroups = useMemo<TagGroup[]>(() => {
    const map = new Map<string, TestCaseListItem[]>()
    for (const c of cases) {
      for (const tagName of c.tags) {
        map.set(tagName, [...(map.get(tagName) ?? []), c])
      }
    }
    const groups: TagGroup[] = []
    for (const [name, list] of map) {
      const tag = registry.get(name)
      groups.push({
        name,
        cases: list,
        color: tag?.color ?? null,
        categoryName: tag?.categoryName ?? null,
      })
    }
    const dir = sortOrder === 'asc' ? 1 : -1
    groups.sort((a, b) =>
      sortKey === 'name'
        ? dir * a.name.localeCompare(b.name, 'zh-CN')
        : dir * (a.cases.length - b.cases.length)
    )
    return groups
  }, [cases, registry, sortKey, sortOrder])

  const paginatedTags = tagGroups.slice(0, tagPage * TAG_LIST_PAGE)

  const toggleTagExpanded = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  if (loading) {
    return (
      <div className='space-y-3'>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
            <Skeleton className='h-11 w-full rounded-none' />
            <div className='space-y-2 p-3'>
              <Skeleton className='h-16 w-full' />
              <Skeleton className='h-16 w-full' />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (tagGroups.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <Tags aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>没有找到标签分组的测试用例</EmptyTitle>
            <EmptyDescription>请为测试用例添加标签</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button size='sm' onClick={onCreate}>
              + 新增用例
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    )
  }

  return (
    <div className={cn('space-y-3 transition-opacity', dimmed && 'opacity-60')}>
      {/* 列表头：全选 + 已选择计数 + 标签排序 */}
      <div className='flex items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          <Checkbox
            checked={cases.length > 0 && cases.every((c) => selected.has(c.id))}
            aria-label='全选用例'
            onCheckedChange={(c) => onToggleAll(cases.map((x) => x.id), c)}
          />
          <p className='text-muted-foreground text-xs'>
            {selected.size > 0 ? `已选择 ${selected.size} 个用例` : '全选以进行批量操作'}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant='outline' size='sm' className='h-8 gap-1.5 px-2.5 font-normal' />
            }
          >
            <ArrowUpDown aria-hidden='true' className='size-3.5' />
            <span className='text-muted-foreground'>排序</span>
            <span className='max-w-24 truncate font-medium'>
              {sortKey === 'count' ? '按用例数量' : '按标签名称'}
              {sortOrder === 'asc' ? '（升序）' : '（降序）'}
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end' className='w-48'>
            <DropdownMenuGroup>
              <DropdownMenuLabel>标签排序</DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            {(
              [
                ['count', '按用例数量'],
                ['name', '按标签名称'],
              ] as Array<[TagSortKey, string]>
            ).map(([key, label]) => (
              <DropdownMenuItem key={key} onSelect={() => setSortKey(key)}>
                {label}
                {sortKey === key && <span className='ms-auto font-medium'>✓</span>}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}>
              顺序：{sortOrder === 'asc' ? '升序 → 降序' : '降序 → 升序'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {paginatedTags.map((group) => {
        const isExpanded = expanded.has(group.name)
        const groupSelected = group.cases.filter((c) => selected.has(c.id)).length
        const subView = tagSubView[group.name] ?? 'flat'
        return (
          <div key={group.name} className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
            <div
              className='flex cursor-pointer items-center justify-between gap-2 px-3 py-2'
              onClick={() => toggleTagExpanded(group.name)}
            >
              <div className='flex min-w-0 items-center gap-2'>
                <Checkbox
                  checked={group.cases.length > 0 && groupSelected === group.cases.length}
                  aria-label={`全选标签 ${group.name}`}
                  onCheckedChange={(c) => onToggleAll(group.cases.map((x) => x.id), c)}
                />
                <ChevronDown
                  aria-hidden='true'
                  className={cn('size-4 text-muted-foreground transition-transform', !isExpanded && '-rotate-90')}
                />
                <span
                  aria-hidden='true'
                  className='size-2 shrink-0 rounded-full'
                  style={{ backgroundColor: group.color ?? '#94a3b8' }}
                />
                <span className='font-medium truncate'>{group.name}</span>
                {group.categoryName && (
                  <span className='text-muted-foreground text-xs'>{group.categoryName}</span>
                )}
                <Badge variant='secondary' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
                  {group.cases.length} 条
                </Badge>
              </div>
              {/* 标签卡组头右区：子视图切换（§3.6，常显） */}
              <div className='flex shrink-0 flex-wrap items-center gap-1.5' onClick={(e) => e.stopPropagation()}>
                <CaseSubViewToggle
                  value={subView}
                  onValueChange={(v) => setTagSubView(group.name, v as 'flat' | 'byGroup')}
                  options={TAG_SUB_VIEW_OPTIONS}
                />
              </div>
            </div>
            {isExpanded && (
              <div className='space-y-2 border-t px-3 py-3'>
                {subView === 'byGroup' ? (
                  group.cases.every((c) => !c.groupId) ? (
                    <Empty className='py-8'>
                      <EmptyMedia variant='icon'>
                        <FolderOpen aria-hidden='true' />
                      </EmptyMedia>
                      <EmptyHeader>
                        <EmptyTitle>该标签下用例均未设置分组</EmptyTitle>
                        <EmptyDescription>切换回「平铺」可查看该标签全部用例</EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  ) : (
                    <div className='space-y-2'>
                      {groupCasesByCaseGroup(group.cases).map((g) => (
                        <div key={g.key} className='space-y-2'>
                          <CaseSubGroupHeader group={g} muted={g.key === '__ungrouped__'} />
                          <div className='space-y-2'>
                            {g.cases.map((c) => (
                              <CaseCard
                                key={c.id}
                                caseItem={c}
                                selected={selected.has(c.id)}
                                tagRegistry={tagRegistry}
                                callbacks={callbacks}
                                onToggleSelect={onToggleSelect}
                              />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                ) : (
                  group.cases.map((c) => (
                    <CaseCard
                      key={c.id}
                      caseItem={c}
                      selected={selected.has(c.id)}
                      tagRegistry={tagRegistry}
                      callbacks={callbacks}
                      onToggleSelect={onToggleSelect}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* 标签分页（加载更多） */}
      {tagGroups.length > tagPage * TAG_LIST_PAGE && (
        <div className='py-1 text-center'>
          <button
            type='button'
            className='text-muted-foreground hover:text-foreground text-xs transition-colors'
            onClick={() => setTagPage((p) => p + 1)}
          >
            已显示 {paginatedTags.length} / {tagGroups.length} 个标签 · 加载更多
          </button>
        </div>
      )}
      {tagGroups.length <= tagPage * TAG_LIST_PAGE && tagGroups.length > 0 && (
        <p className='text-muted-foreground py-1 text-center text-xs'>
          已加载全部 {tagGroups.length} 个标签
        </p>
      )}
    </div>
  )
}
