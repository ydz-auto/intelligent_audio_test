/**
 * 分组视图卡片流（V9.7.10 TestCaseListContainer.vue 分组视图等价移植，11_用例域.md §3.5）。
 * 分组卡：组头（勾选全选 + ChevronDown 展开/折叠 + 分组名 + 计数 Badge + 总时长徽章 +
 * CaseGroupActions 组操作面板：编辑/删除/新增用例/复制/批量修改九项）+ 组内用例卡
 * （懒加载分页：每页 5 条 +「已显示 {n} / {总} 条 · 加载更多」）。
 * 列表级：排序（按用例数量/分组名称/创建时间 × 升降序）+ 分组分页（每页 5 组 + 加载更多）。
 * 「未分组」虚拟组（INT-249：计数=可见数据集中 groupId 为空的用例数；收藏/回收站态不挂载）。
 * 展开态持久化：本会话内存；默认收起（INT-1027 走查裁定：进入页面/筛选变化后分组默认 collapsed，
 * 用户点组头展开后会话内保持展开态——INT-490 P2 默认全展开口径废弃）。
 */
import { ArrowUpDown, ChevronDown, Clock3, FolderOpen, SearchX, Tags, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
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
import { useMediaQuery } from '@/hooks/use-media-query'
import { groupCasesByTag } from '@/domain/lib/sub-view-aggregation'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import { formatCaseDuration } from '@/features/testcases/constants'
import { CaseCard, type CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { CaseGroupActions } from '@/features/testcases/components/case-group-actions'
import {
  CaseSubViewToggle,
  GROUP_SUB_VIEW_OPTIONS,
  SubViewDisplayMenu,
  type SubViewValue,
} from '@/features/testcases/components/case-sub-view-toggle'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import type { BatchActionKey } from '@/features/testcases/components/case-bulk-actions'

/** 组内懒加载每页条数（V9.7.10 itemsPerPage=5 语义平移） */
const GROUP_INLINE_PAGE = 5
/** 分组分页每页组数（V9.7.10 itemsPerPage=5 语义平移） */
const GROUP_LIST_PAGE = 5

type GroupSortKey = 'count' | 'name' | 'createdAt'

/** 分组级操作回调（index 页级装配，弹窗/toast 演示） */
export interface GroupActionCallbacks {
  /** group 为 null 表示未分组/无预填分组（新增用例抽屉不预填分组） */
  onCreateInGroup: (group: TestCaseGroup | null) => void
  onEditGroup: (group: TestCaseGroup) => void
  onDeleteGroup: (group: TestCaseGroup) => void
  onCopyGroup: (group: TestCaseGroup) => void
}

export function GroupedCaseList({
  groups,
  cases,
  loading,
  trash,
  hasQueryFilters,
  selected,
  tagRegistry,
  callbacks,
  onBatchAction,
  actionCallbacks,
  onToggleSelect,
  onToggleAll,
}: {
  groups: TestCaseGroup[]
  cases: TestCaseListItem[]
  loading: boolean
  trash: boolean
  /** 非回收站筛选是否激活（搜索/分组/标签/维度）——回收站空态区分「真空」与「筛选无匹配」 */
  hasQueryFilters: boolean
  selected: Set<string>
  tagRegistry: TagItem[]
  callbacks: CaseCardCallbacks
  onBatchAction: (action: BatchActionKey, ids: string[]) => void
  actionCallbacks: GroupActionCallbacks
  onToggleSelect: (id: string, checked: boolean) => void
  onToggleAll: (ids: string[], checked: boolean) => void
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupPage, setGroupPage] = useState(1)
  const [sortKey, setSortKey] = useState<GroupSortKey>('count')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  /** 组内懒加载已显示计数（每页 GROUP_INLINE_PAGE；未记录=首页） */
  const [inlineCounts, setInlineCounts] = useState<Record<string, number>>({})
  /** 分组卡子视图（§3.5 会话内存 per-group，缺省 flat） */
  const groupSubView = useSessionMap((s) => s.groupSubView)
  const setGroupSubView = useSessionMap((s) => s.setGroupSubView)
  /** §3.3.3：isFetching 时列表不消失、降透明度（placeholderData 保上一帧） */
  const fetching = useIsFetching({ queryKey: ['testcases'] })
  const dimmed = fetching > 0 && !loading
  /** §3.5 移动端（≤640px）子视图切换收进 CaseGroupActions 下拉首项「显示方式」 */
  const isMobile = useMediaQuery('(max-width: 640px)')

  const groupCases = useMemo(() => {
    const map = new Map<string, TestCaseListItem[]>()
    for (const c of cases) {
      const key = c.groupId ?? '__ungrouped__'
      map.set(key, [...(map.get(key) ?? []), c])
    }
    return map
  }, [cases])

  const ungroupedCases = groupCases.get('__ungrouped__') ?? []

  const sortedGroups = useMemo(() => {
    const list = [...groups]
    const dir = sortOrder === 'asc' ? 1 : -1
    switch (sortKey) {
      case 'name':
        list.sort((a, b) => dir * a.name.localeCompare(b.name, 'zh-CN'))
        break
      case 'createdAt':
        list.sort((a, b) => dir * (a.createdAt ?? '').localeCompare(b.createdAt ?? ''))
        break
      default:
        list.sort((a, b) => dir * (a.testCaseCount - b.testCaseCount))
    }
    return list
  }, [groups, sortKey, sortOrder])

  const paginatedGroups = sortedGroups.slice(0, groupPage * GROUP_LIST_PAGE)

  const toggleGroupExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (loading) {
    return (
      <div className='space-y-3'>
        {Array.from({ length: 4 }).map((_, i) => (
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

  /**
   * 空态三态（§3.3 INT-592 平铺流文案）：回收站空 → 筛选无匹配 → 全空。
   * 以可见用例集为准——筛选把全部用例排除后即使分组列表非空也走空态（INT-595 补）。
   */
  if (cases.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            {trash ? (
              <Trash2 aria-hidden='true' />
            ) : groups.length === 0 ? (
              <FolderOpen aria-hidden='true' />
            ) : (
              <SearchX aria-hidden='true' />
            )}
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {trash
                ? hasQueryFilters
                  ? '没有找到符合条件的回收站用例'
                  : '回收站为空'
                : '没有找到符合条件的测试用例'}
            </EmptyTitle>
            <EmptyDescription>
              {trash
                ? hasQueryFilters
                  ? '尝试清空「分组」「标签」等筛选条件'
                  : '回收站中的用例已被恢复或彻底删除'
                : groups.length === 0
                  ? '请调整筛选条件或点击右上角「新增用例」创建第一条用例'
                  : '尝试清空「分组」「标签」筛选'}
            </EmptyDescription>
          </EmptyHeader>
          {!trash && (
            <EmptyContent>
              <Button size='sm' onClick={() => actionCallbacks.onCreateInGroup(null)}>
                + 新增用例
              </Button>
            </EmptyContent>
          )}
        </Empty>
      </div>
    )
  }

  const renderCaseCard = (c: TestCaseListItem) => (
    <CaseCard
      key={c.id}
      caseItem={c}
      selected={selected.has(c.id)}
      tagRegistry={tagRegistry}
      callbacks={callbacks}
      onToggleSelect={onToggleSelect}
    />
  )

  /** 组内内容区：平铺（懒加载分页）或 按标签子视图（§3.5 客户端聚合；「未设置标签」桶末尾弱化） */
  const renderGroupBody = (list: TestCaseListItem[], subView: 'flat' | 'byTag') => {
    if (subView === 'byTag') {
      if (list.every((c) => c.tags.length === 0)) {
        return (
          <Empty className='py-8'>
            <EmptyMedia variant='icon'>
              <Tags aria-hidden='true' />
            </EmptyMedia>
            <EmptyHeader>
              <EmptyTitle>该分组下用例均未设置标签</EmptyTitle>
              <EmptyDescription>切换回「平铺」可查看该分组全部用例</EmptyDescription>
            </EmptyHeader>
          </Empty>
        )
      }
      const groups = groupCasesByTag(list, tagRegistry)
      return (
        <div className='space-y-2'>
          {groups.map((g) => (
            <div key={g.key} className='space-y-2'>
              <CaseSubGroupHeader group={g} muted={g.key === '__untagged__'} />
              <div className='space-y-2'>{g.cases.map(renderCaseCard)}</div>
            </div>
          ))}
        </div>
      )
    }
    return <div className='space-y-2'>{list.map(renderCaseCard)}</div>
  }

  const renderGroupCard = (group: TestCaseGroup) => {
    const list = groupCases.get(group.id) ?? []
    if (list.length === 0) return null
    const isExpanded = expanded.has(group.id)
    const inlineCount = inlineCounts[group.id] ?? GROUP_INLINE_PAGE
    const shownCount = Math.min(inlineCount, list.length)
    const groupDuration = list.reduce((sum, c) => sum + (c.totalDuration ?? 0), 0)
    const groupSelected = list.filter((c) => selected.has(c.id)).length
    const subView = groupSubView[group.id] ?? 'flat'
    const visibleList = list.slice(0, shownCount)

    return (
      <div key={group.id} className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
        <div
          className='flex cursor-pointer items-center justify-between gap-2 px-3 py-2'
          onClick={() => toggleGroupExpanded(group.id)}
        >
          <div className='flex min-w-0 items-center gap-2'>
            <Checkbox
              checked={list.length > 0 && groupSelected === list.length}
              aria-label={`全选分组 ${group.name}`}
              onCheckedChange={(c) => onToggleAll(list.map((x) => x.id), c)}
            />
            <ChevronDown
              aria-hidden='true'
              className={cn('size-4 text-muted-foreground transition-transform', !isExpanded && '-rotate-90')}
            />
            <span className='font-medium truncate'>{group.name}</span>
            <Badge variant='secondary' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
              {list.length} 条
            </Badge>
            {groupDuration > 0 && (
              <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
                <Clock3 aria-hidden='true' className='size-3' />
                总时长 {formatCaseDuration(groupDuration)}
              </Badge>
            )}
          </div>
          {/* 组头右区：子视图切换（计数/时长徽章之后、CaseGroupActions 之前，常显） */}
          <div className='flex shrink-0 flex-wrap items-center gap-1.5' onClick={(e) => e.stopPropagation()}>
            {!isMobile && (
              <CaseSubViewToggle
                value={subView}
                onValueChange={(v) => setGroupSubView(group.id, v as 'flat' | 'byTag')}
                options={GROUP_SUB_VIEW_OPTIONS}
              />
            )}
            {/* 移动端回收站态 CaseGroupActions 隐藏，子视图切换仍保「显示方式」下拉（不回归桌面态） */}
            {isMobile && trash && (
              <SubViewDisplayMenu
                value={subView}
                onValueChange={(v) => setGroupSubView(group.id, v as 'flat' | 'byTag')}
                options={GROUP_SUB_VIEW_OPTIONS}
              />
            )}
            <CaseGroupActions
              name={group.name}
              caseIds={list.map((x) => x.id)}
              selectedIds={list.filter((x) => selected.has(x.id)).map((x) => x.id)}
              trash={trash}
              onEditGroup={() => actionCallbacks.onEditGroup(group)}
              onDeleteGroup={() => actionCallbacks.onDeleteGroup(group)}
              onCreateInGroup={() => actionCallbacks.onCreateInGroup(group)}
              onCopyGroup={() => actionCallbacks.onCopyGroup(group)}
              onBatchAction={onBatchAction}
              subViewMenu={
                isMobile && !trash
                  ? {
                      value: subView as SubViewValue,
                      onValueChange: (v) => setGroupSubView(group.id, v as 'flat' | 'byTag'),
                      options: GROUP_SUB_VIEW_OPTIONS,
                    }
                  : undefined
              }
            />
          </div>
        </div>
        {isExpanded && (
          <div className='space-y-2 border-t px-3 py-3'>
            {renderGroupBody(visibleList, subView)}
            {list.length > shownCount && (
              <button
                type='button'
                className='text-muted-foreground hover:text-foreground w-full py-1 text-xs transition-colors'
                onClick={() =>
                  setInlineCounts((prev) => ({
                    ...prev,
                    [group.id]: (prev[group.id] ?? GROUP_INLINE_PAGE) + GROUP_INLINE_PAGE,
                  }))
                }
              >
                已显示 {shownCount} / {list.length} 条 · 加载更多
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={cn('space-y-3 transition-opacity', dimmed && 'opacity-60')}>
      {/* 列表头：全选 + 已选择计数 + 排序 */}
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
              {sortKey === 'count' ? '按用例数量' : sortKey === 'name' ? '按分组名称' : '按创建时间'}
              {sortOrder === 'asc' ? '（升序）' : '（降序）'}
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end' className='w-48'>
            <DropdownMenuGroup>
              <DropdownMenuLabel>分组排序</DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            {(
              [
                ['count', '按用例数量'],
                ['name', '按分组名称'],
                ['createdAt', '按创建时间'],
              ] as Array<[GroupSortKey, string]>
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

      {paginatedGroups.map(renderGroupCard)}

      {/* 未分组虚拟组（INT-249；同样支持子视图切换 §3.5；INT-1027 默认收起、组头可展开） */}
      {ungroupedCases.length > 0 && (
        <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
          <div
            className='flex cursor-pointer items-center justify-between gap-2 px-3 py-2'
            onClick={() => toggleGroupExpanded('__ungrouped__')}
          >
            <div className='flex min-w-0 items-center gap-2'>
              <Checkbox
                checked={ungroupedCases.length > 0 && ungroupedCases.every((c) => selected.has(c.id))}
                aria-label='全选未分组用例'
                onCheckedChange={(c) => onToggleAll(ungroupedCases.map((x) => x.id), c)}
              />
              <ChevronDown
                aria-hidden='true'
                className={cn(
                  'size-4 text-muted-foreground transition-transform',
                  !expanded.has('__ungrouped__') && '-rotate-90'
                )}
              />
              <span className='font-medium truncate'>未分组</span>
              <Badge variant='secondary' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
                {ungroupedCases.length} 条
              </Badge>
            </div>
            <div
              className='flex shrink-0 flex-wrap items-center gap-1.5'
              onClick={(e) => e.stopPropagation()}
            >
              {!isMobile && (
                <CaseSubViewToggle
                  value={groupSubView['__ungrouped__'] ?? 'flat'}
                  onValueChange={(v) => setGroupSubView('__ungrouped__', v as 'flat' | 'byTag')}
                  options={GROUP_SUB_VIEW_OPTIONS}
                />
              )}
              {isMobile && trash && (
                <SubViewDisplayMenu
                  value={groupSubView['__ungrouped__'] ?? 'flat'}
                  onValueChange={(v) => setGroupSubView('__ungrouped__', v as 'flat' | 'byTag')}
                  options={GROUP_SUB_VIEW_OPTIONS}
                />
              )}
              <CaseGroupActions
                name='未分组'
                caseIds={ungroupedCases.map((x) => x.id)}
                selectedIds={ungroupedCases.filter((x) => selected.has(x.id)).map((x) => x.id)}
                trash={trash}
                onCreateInGroup={() => actionCallbacks.onCreateInGroup(null)}
                onBatchAction={onBatchAction}
                subViewMenu={
                  isMobile && !trash
                    ? {
                        value: (groupSubView['__ungrouped__'] ?? 'flat') as SubViewValue,
                        onValueChange: (v) => setGroupSubView('__ungrouped__', v as 'flat' | 'byTag'),
                        options: GROUP_SUB_VIEW_OPTIONS,
                      }
                    : undefined
                }
              />
            </div>
          </div>
          {expanded.has('__ungrouped__') && (
            <div className='space-y-2 border-t px-3 py-3'>
              {renderGroupBody(ungroupedCases, groupSubView['__ungrouped__'] ?? 'flat')}
            </div>
          )}
        </div>
      )}

      {/* 分组分页（加载更多） */}
      {sortedGroups.length > groupPage * GROUP_LIST_PAGE && (
        <div className='py-1 text-center'>
          <button
            type='button'
            className='text-muted-foreground hover:text-foreground text-xs transition-colors'
            onClick={() => setGroupPage((p) => p + 1)}
          >
            已显示 {paginatedGroups.length} / {sortedGroups.length} 个分组 · 加载更多
          </button>
        </div>
      )}
      {sortedGroups.length <= groupPage * GROUP_LIST_PAGE && sortedGroups.length > 0 && (
        <p className='text-muted-foreground py-1 text-center text-xs'>
          已加载全部 {sortedGroups.length} 个分组
        </p>
      )}
    </div>
  )
}
