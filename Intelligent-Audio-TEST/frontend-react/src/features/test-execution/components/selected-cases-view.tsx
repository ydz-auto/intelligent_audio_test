/**
 * 步骤一「只显示已选中」视图（interfaces/features/test-execution/components；10_测试执行.md §3.5）。
 * 选择态复核专用：只呈现已勾选用例，按当前视图页签分组（按分组 = groupId/groupName 聚合，
 * 按标签 = tags 聚合），组内仍是全站统一用例卡（CaseCard，勾选框可即时取消勾选并移出视图）。
 * 分组/标签聚合复用 domain/lib/sub-view-aggregation 的同一组纯函数（与用例管理子视图同口径），
 * 组头复用 CaseSubGroupHeader，不另造卡片样式。
 * 已选用例可能被当前筛选排除（筛选与选择集独立），汇总行显式提示被排除条数，不静默隐藏。
 */
import { ListChecks } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ComponentProps } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
  type CaseSubGroup,
} from '@/domain/lib/sub-view-aggregation'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import {
  CaseCard,
  type CaseCardCallbacks,
} from '@/features/testcases/components/case-card'
import {
  CaseListErrorBanner,
  CaseListErrorState,
} from '@/features/testcases/components/case-list-error'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import {
  CaseGroupCard,
  type GroupActionCallbacks,
} from '@/features/testcases/components/grouped-case-list'
import { SELECTED_ONLY_COPY } from '@/features/test-execution/constants'
import {
  TEST_CASES_TABS,
  UNGROUPED_GROUP_ID,
  type TestCasesViewKey,
} from '@/features/testcases/constants'

/** 「未设置标签」桶 key（domain/lib/sub-view-aggregation 的固定桶名，组头弱化展示） */
const UNTAGGED_BUCKET_KEY = '__untagged__'

/** 复用用例管理页分组卡的入参（filters/trash/onBatchAction/actions） */
type GroupCardProps = ComponentProps<typeof CaseGroupCard>

export interface SelectedCasesViewProps {
  /** 当前视图页签：按分组 / 按标签 */
  view: TestCasesViewKey
  /** 当前筛选下已勾选的用例行（useSelectedCases 求交结果） */
  cases: TestCaseListItem[]
  /** 全量取数中 */
  loading: boolean
  /** 全量取数失败 */
  isError: boolean
  onRetry: () => void
  /** 返回全部用例列表（关闭「只显示已选中」） */
  onExit: () => void
  /** 已勾选总数（含被当前筛选排除的；用于空态判别与「另有 n 条」提示） */
  selectedCount: number
  tagRegistry: TagItem[]
  /** 算法类型码 → 中文名（缺项时卡片不渲染算法徽章） */
  algorithmLabels?: Record<string, string>
  /** 行内五钮回调；不传（readOnly 观察态）→ 卡片不渲染操作钮 */
  callbacks?: CaseCardCallbacks
  /** 勾选切换；不传（readOnly 观察态）→ 卡片不渲染勾选框 */
  onToggleSelect?: (id: string, checked: boolean) => void
  /** 真实分组（按分组视图复用原分组卡：名称/更新于/操作面板与用例管理页一致） */
  allGroups: TestCaseGroup[]
  /** 当前生效筛选（分组卡组内懒加载/组操作共用） */
  filters: GroupCardProps['filters']
  trash: boolean
  onBatchAction: GroupCardProps['onBatchAction']
  /** 分组级操作回调（页级，按分组装配）；不传 → 分组卡不渲染操作面板（只读观察态） */
  groupActions?: GroupActionCallbacks
}

export function SelectedCasesView({
  view,
  cases,
  loading,
  isError,
  onRetry,
  onExit,
  selectedCount,
  tagRegistry,
  algorithmLabels,
  callbacks,
  onToggleSelect,
  allGroups,
  filters,
  trash,
  onBatchAction,
  groupActions,
}: SelectedCasesViewProps) {
  const groups = useMemo<CaseSubGroup<TestCaseListItem>[]>(
    () =>
      view === 'by-tag'
        ? groupCasesByTag(cases, tagRegistry)
        : groupCasesByCaseGroup(cases),
    [view, cases, tagRegistry]
  )
  /** 按分组视图展开态（默认折叠，与用例管理页分组卡一致） */
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const selected = useMemo(() => new Set(cases.map((c) => c.id)), [cases])
  const groupById = useMemo(
    () => new Map(allGroups.map((g) => [g.id, g])),
    [allGroups]
  )
  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const viewLabel =
    TEST_CASES_TABS.find((tab) => tab.key === view)?.label ?? view
  /** 已勾选但被当前筛选排除的条数（不静默吞掉，汇总行显式提示） */
  const hiddenByFilter = Math.max(selectedCount - cases.length, 0)

  if (loading) {
    return (
      <div className='space-y-3'>
        {Array.from({ length: 2 }).map((_, index) => (
          <div
            key={index}
            className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'
          >
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

  // 取数失败且无可渲染数据：显式错误态 + 重试，不复用「还没有已选中的用例」空态
  if (isError && cases.length === 0) {
    return (
      <CaseListErrorState
        title='已选用例加载失败'
        description='已选用例获取失败，请重试'
        onRetry={onRetry}
      />
    )
  }

  if (cases.length === 0) {
    const filteredOut = selectedCount > 0
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[320px]'>
          <EmptyMedia variant='icon'>
            <ListChecks aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>
              {filteredOut
                ? SELECTED_ONLY_COPY.emptyFilteredTitle
                : SELECTED_ONLY_COPY.emptyTitle}
            </EmptyTitle>
            <EmptyDescription>
              {filteredOut
                ? SELECTED_ONLY_COPY.emptyFilteredDescription
                : SELECTED_ONLY_COPY.emptyDescription}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button size='sm' onClick={onExit}>
              {SELECTED_ONLY_COPY.exit}
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    )
  }

  return (
    <div className='space-y-3'>
      {isError && (
        <CaseListErrorBanner
          message='已选用例加载失败，当前显示的是上一次加载的数据'
          onRetry={onRetry}
        />
      )}
      <div className='bg-card/50 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2'>
        <ListChecks aria-hidden='true' className='size-3.5' />
        <span className='text-sm font-medium'>{SELECTED_ONLY_COPY.title}</span>
        <Badge variant='secondary' className='rounded-md text-[11px]'>
          {viewLabel} · {SELECTED_ONLY_COPY.summary(cases.length)}
        </Badge>
        {hiddenByFilter > 0 && (
          <span className='text-muted-foreground text-xs'>
            {SELECTED_ONLY_COPY.hiddenByFilter(hiddenByFilter)}
          </span>
        )}
        <Button
          variant='ghost'
          size='sm'
          className='ms-auto h-7 text-xs'
          onClick={onExit}
        >
          {SELECTED_ONLY_COPY.exit}
        </Button>
      </div>

      <div className='space-y-4'>
        {groups.map((group) => {
          const realGroup =
            view === 'by-group' ? groupById.get(group.key) : undefined
          // 按分组视图：直接复用用例管理页原分组卡（编辑/删除/新增用例/复制/批量修改/子视图切换）
          if (realGroup) {
            return (
              <CaseGroupCard
                key={group.key}
                group={{
                  ...realGroup,
                  testCaseCount: group.cases.length,
                  totalDuration: group.totalDuration,
                }}
                filters={filters}
                expanded={expanded.has(group.key)}
                onToggleExpanded={() => toggleExpanded(group.key)}
                selected={selected}
                tagRegistry={tagRegistry}
                algorithmLabels={algorithmLabels}
                trash={trash}
                callbacks={callbacks}
                actions={
                  groupActions
                    ? {
                        onCreateInGroup: () => groupActions.onCreateInGroup(realGroup),
                        onEditGroup: () => groupActions.onEditGroup(realGroup),
                        onDeleteGroup: () => groupActions.onDeleteGroup(realGroup),
                        onCopyGroup: () => groupActions.onCopyGroup(realGroup),
                      }
                    : undefined
                }
                onBatchAction={onBatchAction}
                onToggleSelect={onToggleSelect}
                controlledCases={group.cases}
              />
            )
          }
          // 按标签视图 / 未分组桶：保持只读子分组头 + 统一用例卡
          return (
            <section key={group.key} className='space-y-2'>
              <CaseSubGroupHeader
                group={group}
                muted={
                  group.key === UNTAGGED_BUCKET_KEY ||
                  group.key === UNGROUPED_GROUP_ID
                }
              />
              <div className='space-y-2'>
                {group.cases.map((caseItem) => (
                  <CaseCard
                    key={caseItem.id}
                    caseItem={caseItem}
                    selected
                    tagRegistry={tagRegistry}
                    algorithmLabels={algorithmLabels}
                    callbacks={callbacks}
                    onToggleSelect={onToggleSelect}
                  />
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
