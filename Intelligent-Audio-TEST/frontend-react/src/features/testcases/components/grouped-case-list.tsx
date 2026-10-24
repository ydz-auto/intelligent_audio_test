/**
 * 分组视图卡片流（V9.7.10 TestCaseListContainer.vue 分组视图等价移植，11_用例域.md §3.5）。
 * 分组卡：组头（勾选全选 + ChevronDown 展开/折叠 + 分组名 + 计数 Badge + 总时长徽章 +
 * CaseGroupActions 组操作面板：编辑/删除/新增用例/复制/批量修改九项）+ 组内用例卡
 * （组内懒加载分页：按 group_id 懒拉 GROUP_PAGE_SIZE 条 +「已显示 {n} / {总} 条 · 加载更多」）。
 * INT-1267 修复：分组卡以 /groups 全部分组渲染（空组也渲染、计数用 testCaseCount），
 * 组内用例展开时按组懒加载（Vue testCaseStore.fetchCasesByGroup 对位）——分组卡是否渲染
 * 不再由「当前已加载用例页」决定，其余分组与未分组卡始终可见、可展开浏览/勾选。
 * 审计返修：组头全选传 group 分组名（P1）、生效筛选合并全局算法进组内懒加载/组头全选（P2）、
 * 未分组哨兵筛选由虚拟组承接（P3）、收藏视图组头全选降级为已加载用例（P3）。
 * 列表级：排序（按用例数量/分组名称/创建时间 × 升降序）+ 分组分页（每页 5 组 + 加载更多）。
 * 「未分组」虚拟组（INT-249：计数=可见数据集中 groupId 为空的用例数；/groups 已含「未分组」
 * 条目时不重复渲染；收藏/回收站态不挂载）。
 * 展开态持久化：本会话内存；默认收起（INT-1027 走查裁定：进入页面/筛选变化后分组默认 collapsed，
 * 用户点组头展开后会话内保持展开态——INT-490 P2 默认全展开口径废弃）。
 */
import { ArrowUpDown, ChevronDown, Clock3, FolderOpen, SearchX, Tags, Trash2 } from 'lucide-react'
import { useMemo, useState, useEffect } from 'react'
import { useIsFetching } from '@tanstack/react-query'

import { useCaseRoundsRegistry } from '@/application/testcases/case-rounds-registry'
import { useSessionMap, type GroupSubView } from '@/application/testcases/use-session-map'
import { useGroupCases } from '@/application/testcases/use-group-cases'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
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
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { useMediaQuery } from '@/hooks/use-media-query'
import { groupCasesByTag } from '@/domain/lib/sub-view-aggregation'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import { formatCaseDuration, UNGROUPED_GROUP_ID } from '@/features/testcases/constants'
import { CaseCard, type CaseCardCallbacks } from '@/features/testcases/components/case-card'
import {
  CaseListErrorBanner,
  CaseListErrorState,
} from '@/features/testcases/components/case-list-error'
import { CaseGroupActions } from '@/features/testcases/components/case-group-actions'
import { fetchCaseIdsByFilter } from '@/infrastructure/api/testcases-ids-api'
import {
  CaseSubViewToggle,
  GROUP_SUB_VIEW_OPTIONS,
  SubViewDisplayMenu,
  type SubViewValue,
} from '@/features/testcases/components/case-sub-view-toggle'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import type { BatchActionKey } from '@/features/testcases/components/case-bulk-actions'

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

/** 单张分组卡操作面板回调（GroupCard 内按组装配；未分组虚拟组只给 onCreateInGroup） */
interface GroupCardActions {
  onCreateInGroup?: () => void
  onEditGroup?: () => void
  onDeleteGroup?: () => void
  onCopyGroup?: () => void
}

/** 组卡属性（真实分组与未分组虚拟组共用；未分组用合成 TestCaseGroup） */
interface GroupCardProps {
  group: TestCaseGroup
  filters: TestCaseListFilters
  expanded: boolean
  onToggleExpanded: () => void
  selected: Set<string>
  tagRegistry: TagItem[]
  /** 算法类型码 → 中文名（真实 /algorithm/options；缺项时卡片不渲染算法徽章） */
  algorithmLabels?: Record<string, string>
  trash: boolean
  /** 行内五钮回调；不传（readOnly 观察态）→ 卡片不渲染操作钮 */
  callbacks?: CaseCardCallbacks
  /** 组操作面板回调；不传（readOnly 观察态）→ 组头操作面板隐藏 */
  actions?: GroupCardActions
  onBatchAction: (action: BatchActionKey, ids: string[]) => void
  /** 勾选切换；不传（readOnly 观察态）→ 卡片/组头勾选框隐藏 */
  onToggleSelect?: (id: string, checked: boolean) => void
  onToggleAll?: (ids: string[], checked: boolean) => void
}

function GroupCard({
  group,
  filters,
  expanded,
  onToggleExpanded,
  selected,
  tagRegistry,
  algorithmLabels,
  trash,
  callbacks,
  actions,
  onBatchAction,
  onToggleSelect,
  onToggleAll,
}: GroupCardProps) {
  /** §3.5 移动端（≤640px）子视图切换收进 CaseGroupActions 下拉首项「显示方式」 */
  const isMobile = useMediaQuery('(max-width: 640px)')
  /** §3.5 会话内存 per-group 子视图（缺省 flat） */
  const groupSubView = useSessionMap((s) => s.groupSubView)
  const setGroupSubView = useSessionMap((s) => s.setGroupSubView)
  /** 组内用例懒加载（展开才拉；Vue fetchCasesByGroup 对位，INT-1267） */
  const {
    items: list,
    total,
    hasMore,
    isLoading,
    isFetching,
    isError: groupError,
    refetch: refetchGroup,
    loadMore,
  } = useGroupCases(group.id, filters, expanded)

  /**
   * 组内已加载用例的轮次登记（INT-1506 审返 P2）：组内用例来自按分组懒加载的分页，
   * 不在列表首页 items 里；批量弹窗按选中 id 解析轮次时靠这里的登记，避免「轮次未知」假空态。
   */
  const { register: registerCaseRounds } = useCaseRoundsRegistry()
  useEffect(() => {
    registerCaseRounds(list)
  }, [list, registerCaseRounds])

  const subView = (groupSubView[group.id] ?? 'flat') as GroupSubView
  const groupDuration = list.reduce((sum, c) => sum + (c.totalDuration ?? 0), 0)
  const groupSelected = list.filter((c) => selected.has(c.id)).length

  /**
   * 组头「全选分组」：真实分组经 POST /testcases/ids 按当前筛选圈定全组 ID（Vue toggleGroupSelection
   * 对位——未展开也能全选/取消全选整组）；回收站/收藏态与未分组虚拟组无 /ids 契约映射
   * （fetch_case_ids 不支持 favorite，INT-1267 审计 P3），保持已加载用例圈定。
   * 契约：/testcases/ids body 只认 group 分组**名**（后端 filter_by(name=group)），group_id 会被
   * 忽略导致圈定全库（INT-1267 审计 P1 打回返修）。
   */
  const handleGroupToggleAll = async (checked: boolean) => {
    if (!onToggleAll) return
    if (trash || filters.favorite || group.id === UNGROUPED_GROUP_ID) {
      onToggleAll(list.map((x) => x.id), checked)
      return
    }
    try {
      const { ids } = await fetchCaseIdsByFilter({
        search: filters.search,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        algorithmType: filters.algorithmType,
        group: group.name,
      })
      onToggleAll(ids, checked)
    } catch {
      // 全量 ID 圈定失败降级为已加载用例（组内仍可逐卡勾选）
      onToggleAll(list.map((x) => x.id), checked)
    }
  }

  const renderCaseCard = (c: TestCaseListItem) => (
    <CaseCard
      key={c.id}
      caseItem={c}
      selected={selected.has(c.id)}
      tagRegistry={tagRegistry}
      algorithmLabels={algorithmLabels}
      callbacks={callbacks}
      onToggleSelect={onToggleSelect}
    />
  )

  /** 组内内容区：平铺（懒加载分页）或 按标签子视图（§3.5 客户端聚合；「未设置标签」桶末尾弱化） */
  const renderGroupBody = (listItems: TestCaseListItem[]) => {
    if (subView === 'byTag') {
      if (listItems.every((c) => c.tags.length === 0)) {
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
      const groups = groupCasesByTag(listItems, tagRegistry)
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
    return <div className='space-y-2'>{listItems.map(renderCaseCard)}</div>
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div
        className='flex cursor-pointer items-center justify-between gap-2 px-3 py-2'
        onClick={onToggleExpanded}
      >
        <div className='flex min-w-0 items-center gap-2'>
          {onToggleAll != null && (
            <Checkbox
              checked={list.length > 0 && groupSelected === list.length}
              aria-label={`全选分组 ${group.name}`}
              onCheckedChange={(c) => void handleGroupToggleAll(c)}
            />
          )}
          <ChevronDown
            aria-hidden='true'
            className={cn('size-4 text-muted-foreground transition-transform', !expanded && '-rotate-90')}
          />
          <span className='font-medium truncate'>{group.name}</span>
          <Badge variant='secondary' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
            {group.testCaseCount} 条
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
              value={subView as SubViewValue}
              onValueChange={(v) => setGroupSubView(group.id, v as GroupSubView)}
              options={GROUP_SUB_VIEW_OPTIONS}
            />
          )}
          {/* 移动端回收站态 CaseGroupActions 隐藏，子视图切换仍保「显示方式」下拉（不回归桌面态） */}
          {isMobile && trash && (
            <SubViewDisplayMenu
              value={subView as SubViewValue}
              onValueChange={(v) => setGroupSubView(group.id, v as GroupSubView)}
              options={GROUP_SUB_VIEW_OPTIONS}
            />
          )}
          {actions != null && (
            <CaseGroupActions
              name={group.name}
              caseIds={list.map((x) => x.id)}
              selectedIds={list.filter((x) => selected.has(x.id)).map((x) => x.id)}
              trash={trash}
              onEditGroup={actions.onEditGroup}
              onDeleteGroup={actions.onDeleteGroup}
              onCreateInGroup={actions.onCreateInGroup}
              onCopyGroup={actions.onCopyGroup}
              onBatchAction={onBatchAction}
              subViewMenu={
                isMobile && !trash
                  ? {
                      value: subView as SubViewValue,
                      onValueChange: (v) => setGroupSubView(group.id, v as GroupSubView),
                      options: GROUP_SUB_VIEW_OPTIONS,
                    }
                  : undefined
              }
            />
          )}
        </div>
      </div>
      {expanded && (
        <div className='space-y-2 border-t px-3 py-3'>
          {/* 组内查询失败（INT-1605）：不得渲染成「该分组暂无用例」 */}
          {groupError && list.length > 0 && (
            <CaseListErrorBanner
              message='该分组用例加载失败，当前显示的是已加载的数据'
              onRetry={refetchGroup}
            />
          )}
          {isLoading && list.length === 0 ? (
            <div className='space-y-2'>
              <Skeleton className='h-16 w-full' />
              <Skeleton className='h-16 w-full' />
            </div>
          ) : list.length === 0 && groupError ? (
            <div className='flex flex-col items-center gap-2 py-6 text-center'>
              <p className='text-destructive text-xs'>该分组用例加载失败</p>
              <Button variant='outline' size='sm' className='h-7' onClick={refetchGroup}>
                重试
              </Button>
            </div>
          ) : list.length === 0 ? (
            <p className='text-muted-foreground py-6 text-center text-xs'>
              {trash ? '该分组回收站暂无用例' : '该分组暂无用例'}
            </p>
          ) : (
            renderGroupBody(list)
          )}
          {hasMore && (
            <button
              type='button'
              disabled={isFetching}
              className='text-muted-foreground hover:text-foreground w-full py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-60'
              onClick={loadMore}
            >
              {isFetching
                ? '加载中…'
                : `已显示 ${list.length} / ${total} 条 · 加载更多`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export function GroupedCaseList({
  groups,
  cases,
  loading,
  groupsLoading,
  isError,
  onRetry,
  trash,
  hasQueryFilters,
  filters,
  selected,
  tagRegistry,
  algorithmLabels,
  callbacks,
  onBatchAction,
  actionCallbacks,
  onToggleSelect,
  onToggleAll,
}: {
  groups: TestCaseGroup[]
  cases: TestCaseListItem[]
  loading: boolean
  /** 分组列表加载（INT-1284：分组卡渲染以 /groups 为准；缺省沿用 loading，兼容旧调用） */
  groupsLoading?: boolean
  /** 用例列表查询失败（INT-1605）：失败且无数据时渲染错误态，不得伪装成「没有找到」空态 */
  isError?: boolean
  /** 查询失败重试（refetch） */
  onRetry?: () => void
  trash: boolean
  /** 非回收站筛选是否激活（搜索/分组/标签/维度）——回收站空态区分「真空」与「筛选无匹配」 */
  hasQueryFilters: boolean
  /** 当前生效筛选（搜索/分组/标签/维度/算法/收藏/回收站；组内懒加载共用） */
  filters: TestCaseListFilters
  selected: Set<string>
  tagRegistry: TagItem[]
  /** 算法类型码 → 中文名（真实 /algorithm/options；缺项时卡片不渲染算法徽章） */
  algorithmLabels?: Record<string, string>
  /** 行内五钮回调；不传（readOnly 观察态）→ 卡片不渲染操作钮 */
  callbacks?: CaseCardCallbacks
  onBatchAction: (action: BatchActionKey, ids: string[]) => void
  /** 组操作回调；不传（readOnly 观察态）→ 组头操作面板隐藏 */
  actionCallbacks?: GroupActionCallbacks
  /** 勾选切换；不传（readOnly 观察态）→ 卡片/组头勾选框隐藏 */
  onToggleSelect?: (id: string, checked: boolean) => void
  onToggleAll?: (ids: string[], checked: boolean) => void
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupPage, setGroupPage] = useState(1)
  const [sortKey, setSortKey] = useState<GroupSortKey>('count')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  /** §3.3.3：isFetching 时列表不消失、降透明度（placeholderData 保上一帧） */
  const fetching = useIsFetching({ queryKey: ['testcases'] })
  const dimmed = fetching > 0 && !loading

  const groupCases = useMemo(() => {
    const map = new Map<string, TestCaseListItem[]>()
    for (const c of cases) {
      const key = c.groupId ?? UNGROUPED_GROUP_ID
      map.set(key, [...(map.get(key) ?? []), c])
    }
    return map
  }, [cases])

  const ungroupedCases = groupCases.get(UNGROUPED_GROUP_ID) ?? []
  /** /groups 已含「未分组」真实条目时不重复渲染虚拟组（INT-1267 空组也渲染） */
  const hasNamedUngrouped = useMemo(() => groups.some((g) => g.name === '未分组'), [groups])
  const ungroupedGroup = useMemo<TestCaseGroup | null>(
    () =>
      ungroupedCases.length > 0 &&
      !hasNamedUngrouped &&
      (filters.groupId == null || filters.groupId === UNGROUPED_GROUP_ID)
        ? {
            id: UNGROUPED_GROUP_ID,
            name: '未分组',
            description: null,
            algorithmType: null,
            createdAt: '',
            updatedAt: '',
            testCaseCount: ungroupedCases.length,
          }
        : null,
    [ungroupedCases.length, hasNamedUngrouped, filters.groupId]
  )

  /** 工具栏「分组」筛选激活时只渲染该分组卡（Vue groupFilter 口径；未筛选时全量分组卡）。
   *  未分组哨兵（__ungrouped__）时无真实分组命中 → 空数组，由下方虚拟未分组卡承接
   *  （INT-1267 审计 P3：原先真实分组被滤空、虚拟卡又被 !filters.groupId 守卫抑制 → 空白） */
  const visibleGroups = useMemo(
    () => (filters.groupId ? groups.filter((g) => g.id === filters.groupId) : groups),
    [groups, filters.groupId]
  )

  const sortedGroups = useMemo(() => {
    const list = [...visibleGroups]
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
  }, [visibleGroups, sortKey, sortOrder])

  const paginatedGroups = sortedGroups.slice(0, groupPage * GROUP_LIST_PAGE)

  const toggleGroupExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  /** 真实分组操作面板装配（readOnly 观察态 actionCallbacks 缺省 → 不渲染） */
  const buildGroupActions = (group: TestCaseGroup): GroupCardActions | undefined => {
    if (actionCallbacks == null) return undefined
    return {
      onCreateInGroup: () => actionCallbacks.onCreateInGroup(group),
      onEditGroup: () => actionCallbacks.onEditGroup(group),
      onDeleteGroup: () => actionCallbacks.onDeleteGroup(group),
      onCopyGroup: () => actionCallbacks.onCopyGroup(group),
    }
  }

  // INT-1657：用例列表首屏仍在加载（/testcases 单页真实库 8~20s）时，不得把「还没有数据」
  // 当成「没有找到符合条件的测试用例」——那要等扁平集到位（空/有）才能下结论。
  const casesPending = loading && cases.length === 0

  // INT-1284：骨架以分组列表加载为准（/groups 快）；分组到位后即使用例列表仍加载
  // （/testcases 单页响应慢），也立即渲染分组卡（计数取 test_case_count），不阻塞卡渲染。
  // INT-1657：仅当分组也未到位、或分组筛不出任何卡可渲染时才继续骨架。
  if ((groupsLoading ?? loading) || (casesPending && sortedGroups.length === 0)) {
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

  // 查询失败且无任何可展示用例：显式错误态 + 重试（INT-1605）。
  // 不得落到下方「没有找到符合条件的测试用例」空态——否则接口挂了与库空在 UI 上无法区分。
  if (isError && cases.length === 0) {
    return (
      <CaseListErrorState
        title='用例列表加载失败'
        description='用例列表获取失败，请重试'
        onRetry={onRetry}
      />
    )
  }

  /**
   * 空态三态（§3.3 INT-592 平铺流文案）：回收站空 → 筛选无匹配 → 全空。
   * 以可见用例集为准——筛选把全部用例排除后即使分组列表非空也走空态（INT-595 补）。
   * INT-1267：分组卡渲染不依赖「当前已加载用例页」，故只要列表页还有数据分组卡全量渲染；
   * 空态仍以平铺集为准（真实库列表页首屏恒有数据，空组由 /groups 全量分组卡兜住）。
   * INT-1657：首屏扁平集仍在加载（casesPending）时不得给空态结论，落到下方分组卡流 + 加载提示。
   */
  if (!casesPending && cases.length === 0) {
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
          {!trash && actionCallbacks != null && (
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

  return (
    <div className={cn('space-y-3 transition-opacity', dimmed && 'opacity-60')}>
      {/* 翻页 / 筛选失败但有上次数据：保留旧列表 + 行内提示（INT-1605） */}
      {isError && cases.length > 0 && (
        <CaseListErrorBanner
          message='用例列表加载失败，当前显示的是上一次加载的数据'
          onRetry={onRetry}
        />
      )}
      {/* 用例列表首屏加载中（INT-1657）：分组卡已按 /groups 渲染，扁平集到位前只给加载提示，
          不下「没有找到」结论 */}
      {casesPending && (
        <div role='status' className='text-muted-foreground flex items-center gap-2 text-xs'>
          <Spinner className='size-3.5' />
          用例列表加载中…
        </div>
      )}
      {/* 列表头：全选 + 已选择计数 + 排序 */}
      <div className='flex items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          {onToggleAll != null && (
            <Checkbox
              checked={cases.length > 0 && cases.every((c) => selected.has(c.id))}
              aria-label='全选用例'
              onCheckedChange={(c) => onToggleAll(cases.map((x) => x.id), c)}
            />
          )}
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
              顺序：{sortOrder === 'asc' ? '降序 → 升序' : '升序 → 降序'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {paginatedGroups.map((group) => (
        <GroupCard
          key={group.id}
          group={group}
          filters={filters}
          expanded={expanded.has(group.id)}
          onToggleExpanded={() => toggleGroupExpanded(group.id)}
          selected={selected}
          tagRegistry={tagRegistry}
          algorithmLabels={algorithmLabels}
          trash={trash}
          callbacks={callbacks}
          actions={buildGroupActions(group)}
          onBatchAction={onBatchAction}
          onToggleSelect={onToggleSelect}
          onToggleAll={onToggleAll}
        />
      ))}

      {/* 未分组虚拟组（INT-249；/groups 已有「未分组」真实条目时不重复渲染；
          同样支持子视图切换 §3.5；INT-1027 默认收起、组头可展开） */}
      {ungroupedGroup != null && (
        <GroupCard
          group={ungroupedGroup}
          filters={filters}
          expanded={expanded.has(UNGROUPED_GROUP_ID)}
          onToggleExpanded={() => toggleGroupExpanded(UNGROUPED_GROUP_ID)}
          selected={selected}
          tagRegistry={tagRegistry}
          algorithmLabels={algorithmLabels}
          trash={trash}
          callbacks={callbacks}
          actions={
            actionCallbacks != null
              ? { onCreateInGroup: () => actionCallbacks.onCreateInGroup(null) }
              : undefined
          }
          onBatchAction={onBatchAction}
          onToggleSelect={onToggleSelect}
          onToggleAll={onToggleAll}
        />
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
