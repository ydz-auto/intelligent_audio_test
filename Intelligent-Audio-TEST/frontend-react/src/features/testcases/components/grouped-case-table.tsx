/**
 * 分组视图表格（11_用例域.md §3.5 DataTablePage renderRow 两级渲染）：
 * 分组头行（Collapsible 展开态行）+ 组内用例行；分组头含 计数 Badge/组总时长/组操作菜单/
 * 组全选 Checkbox；「未分组」虚拟组头（INT-249 口径：计数=用例总数−Σ分组计数）；
 * 组内懒加载（现每页 5 条平移为「组内加载更多」行：已显示 {n} / {总} 条 + IntersectionObserver 演示）。
 * 展开态持久化：本会话内存（展开集不进 URL，避免 URL 爆炸）。
 */
import { ChevronDown, MoreHorizontal, Clock3 } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import {
  formatCaseDuration,
  type CaseColumnKey,
} from '@/features/testcases/constants'
import { CaseTableHeader, ViewOptions } from '@/features/testcases/components/case-table-header'
import { CaseTableRow, type CaseRowCallbacks } from '@/features/testcases/components/case-row'

/** 组内懒加载每页条数（现每页 5 条语义平移） */
const GROUP_INLINE_PAGE = 5

export interface GroupActionCallbacks {
  /** group 为 null 表示未分组/无预填分组（新增用例抽屉不预填分组） */
  onCreateInGroup: (group: TestCaseGroup | null) => void
  onEditGroup: (group: TestCaseGroup) => void
  onDeleteGroup: (group: TestCaseGroup) => void
  onCopyGroup: (group: TestCaseGroup) => void
}

function GroupHeaderRow({
  group,
  cases,
  expanded,
  selectedCount,
  onToggleExpanded,
  onToggleGroupSelect,
  actionCallbacks,
}: {
  group: TestCaseGroup
  cases: TestCaseListItem[]
  expanded: boolean
  selectedCount: number
  onToggleExpanded: () => void
  onToggleGroupSelect: (checked: boolean) => void
  actionCallbacks: GroupActionCallbacks
}) {
  const groupDuration = cases.reduce((sum, c) => sum + (c.totalDuration ?? 0), 0)

  return (
    <tr className='bg-[var(--table-header)]'>
      <td className='w-11 px-3 py-2'>
        <Checkbox
          checked={cases.length > 0 && selectedCount === cases.length}
          aria-label={`全选分组 ${group.name}`}
          onCheckedChange={onToggleGroupSelect}
        />
      </td>
      <td colSpan={7} className='px-3 py-2'>
        <div className='flex items-center gap-2'>
          <button
            type='button'
            className='hover:bg-muted flex items-center gap-1.5 rounded-md px-1 py-0.5 text-start'
            onClick={onToggleExpanded}
            aria-expanded={expanded}
          >
            <ChevronDown
              aria-hidden='true'
              className={cn('size-4 transition-transform', !expanded && '-rotate-90')}
            />
            <span className='font-medium'>{group.name}</span>
          </button>
          <Badge variant='secondary' className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
            {cases.length} 条
          </Badge>
          {groupDuration > 0 && (
            <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-mono text-[11px] tabular-nums'>
              <Clock3 aria-hidden='true' className='size-3' />
              总时长 {formatCaseDuration(groupDuration)}
            </Badge>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant='ghost' size='icon-sm' className='size-6' aria-label={`${group.name} 操作`} />
              }
            >
              <MoreHorizontal aria-hidden='true' />
            </DropdownMenuTrigger>
            <DropdownMenuContent align='start' className='w-48'>
              <DropdownMenuItem onSelect={() => actionCallbacks.onEditGroup(group)}>
                编辑分组
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  toast.success('已复制分组', {
                    description: `新分组：${group.name}_copy`,
                  })
                }}
              >
                复制分组
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => actionCallbacks.onCreateInGroup(group)}>
                新增用例到此分组
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem data-variant='destructive' onSelect={() => actionCallbacks.onDeleteGroup(group)}>
                删除分组
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </td>
      <td className='px-3 py-2' />
    </tr>
  )
}

export function GroupedCaseTable({
  groups,
  cases,
  loading,
  selected,
  visible,
  onVisibleChange,
  tagRegistry,
  callbacks,
  actionCallbacks,
  onToggleSelect,
  onToggleAll,
}: {
  groups: TestCaseGroup[]
  cases: TestCaseListItem[]
  loading: boolean
  selected: Set<string>
  visible: Set<CaseColumnKey>
  onVisibleChange: (next: Set<CaseColumnKey>) => void
  tagRegistry: TagItem[]
  callbacks: CaseRowCallbacks
  actionCallbacks: GroupActionCallbacks
  onToggleSelect: (id: string, checked: boolean) => void
  onToggleAll: (ids: string[], checked: boolean) => void
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(groups.map((g) => g.id)))
  const [loaded, setLoaded] = useState<Record<string, number>>({})

  const groupCases = useMemo(() => {
    const map = new Map<string, TestCaseListItem[]>()
    for (const c of cases) {
      const key = c.groupId ?? '__ungrouped__'
      map.set(key, [...(map.get(key) ?? []), c])
    }
    return map
  }, [cases])

  // 未分组虚拟组（INT-249：仅非收藏/回收站态挂载，计数=可见数据集中 groupId 为空的用例数）
  const ungroupedCases = groupCases.get('__ungrouped__') ?? []

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
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  if (cases.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <span className='text-3xl'>🗂️</span>
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>没有找到测试用例分组</EmptyTitle>
            <EmptyDescription>请尝试添加新的测试用例或创建分组</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button size='sm' onClick={() => actionCallbacks.onCreateInGroup(null)}>
              + 新增用例
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    )
  }

  const renderCases = (list: TestCaseListItem[], groupKey: string) => {
    const loadedCount = loaded[groupKey] ?? GROUP_INLINE_PAGE
    const shown = list.slice(0, loadedCount)
    return shown.map((c) => (
      <CaseTableRow
        key={c.id}
        caseItem={c}
        selected={selected.has(c.id)}
        visible={visible}
        tagRegistry={tagRegistry}
        callbacks={callbacks}
        onToggleSelect={onToggleSelect}
      />
    ))
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='flex items-center justify-between gap-2 border-b px-3 py-2'>
        <p className='text-muted-foreground text-xs'>
          {selected.size > 0 ? `已选择 ${selected.size} 个用例` : '全选以进行批量操作'}
        </p>
        <ViewOptions visible={visible} onChange={onVisibleChange} />
      </div>

      <div className='overflow-x-auto'>
        <table className='w-full min-w-[860px] text-[13px]'>
          <CaseTableHeader
            allChecked={cases.length > 0 && cases.every((c) => selected.has(c.id))}
            onToggleAll={(checked) => onToggleAll(cases.map((c) => c.id), checked)}
            visible={visible}
          />
          <tbody>
            {groups.map((group) => {
              const list = groupCases.get(group.id) ?? []
              if (list.length === 0) return null
              const groupSelected = list.filter((c) => selected.has(c.id)).length
              const isExpanded = expanded.has(group.id)
              return (
                <GroupCaseSection
                  key={group.id}
                  group={group}
                  list={list}
                  isExpanded={isExpanded}
                  selectedCount={groupSelected}
                  onToggleExpanded={() => toggleGroupExpanded(group.id)}
                  onToggleGroupSelect={(checked) => onToggleAll(list.map((c) => c.id), checked)}
                  actionCallbacks={actionCallbacks}
                  loadedCount={loaded[group.id] ?? GROUP_INLINE_PAGE}
                  onLoadMore={() => setLoaded((prev) => ({ ...prev, [group.id]: (prev[group.id] ?? GROUP_INLINE_PAGE) + GROUP_INLINE_PAGE }))}
                  renderRows={() => renderCases(list, group.id)}
                />
              )
            })}

            {ungroupedCases.length > 0 && (
              <>
                <GroupHeaderRow
                  group={{ id: '__ungrouped__', name: '未分组', description: null, algorithmType: null, createdAt: '', updatedAt: '', testCaseCount: ungroupedCases.length }}
                  cases={ungroupedCases}
                  expanded={true}
                  selectedCount={ungroupedCases.filter((c) => selected.has(c.id)).length}
                  onToggleExpanded={() => undefined}
                  onToggleGroupSelect={(checked) => onToggleAll(ungroupedCases.map((c) => c.id), checked)}
                  actionCallbacks={{ ...actionCallbacks, onCreateInGroup: actionCallbacks.onCreateInGroup.bind(null, null) }}
                />
                {renderCases(ungroupedCases, '__ungrouped__')}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function GroupCaseSection({
  group,
  list,
  isExpanded,
  selectedCount,
  onToggleExpanded,
  onToggleGroupSelect,
  actionCallbacks,
  loadedCount,
  onLoadMore,
  renderRows,
}: {
  group: TestCaseGroup
  list: TestCaseListItem[]
  isExpanded: boolean
  selectedCount: number
  onToggleExpanded: () => void
  onToggleGroupSelect: (checked: boolean) => void
  actionCallbacks: GroupActionCallbacks
  loadedCount: number
  onLoadMore: () => void
  renderRows: () => ReactNode
}) {
  return (
    <>
      <GroupHeaderRow
        group={group}
        cases={list}
        expanded={isExpanded}
        selectedCount={selectedCount}
        onToggleExpanded={onToggleExpanded}
        onToggleGroupSelect={onToggleGroupSelect}
        actionCallbacks={actionCallbacks}
      />
      {isExpanded && renderRows()}
      {isExpanded && list.length > loadedCount && (
        <tr className='hover:bg-muted/40 border-border/60 border-b'>
          <td colSpan={9} className='px-3 py-2 text-center'>
            <button
              type='button'
              className='text-muted-foreground hover:text-foreground text-xs transition-colors'
              onClick={onLoadMore}
            >
              已显示 {loadedCount} / {list.length} 条 · 加载更多
            </button>
          </td>
        </tr>
      )}
    </>
  )
}
