/**
 * 容器详情「组成」区（18_挑选合并功能交互重设计.md §5.5.3 ② / §5.5.4 / §5.5.6，INT-1711）。
 * 首屏主区，紧跟任务信息卡：四视图（任务视图默认｜用例｜设备｜结果类型）只读呈现
 * 「合并后的任务长什么样」——树复用购物车 `CartTree`（`readOnly`、不渲染复选框、无移除入口），
 * 层级、视觉、计数与购物车 / 复核逐项一致；四视图构建同源（域内 `buildCart*View` + `CartTree view='task'`）。
 * 只读语义：容器是既成事实，不是待下单清单——需要改动的用户走 §5.5.5「复用本次结果重新挑选」。
 * 空态（§5.5.6）：无来源记录 / 筛选无命中 / 只看失效；加载态为信息头骨架 + 树骨架三层。
 * 纯 props，取数在 `useContainerComposition`。
 */
import { Link } from '@tanstack/react-router'
import { AlertTriangle, ListFilter, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import {
  usePickOrg,
} from '@/application/tasks/cherry-pick/use-pick-org'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  filterCompositionEntries,
  filterMissingEntries,
  groupCompositionEntries,
  orgGroupEntries,
  organizeCompositionCases,
  type CompositionEntry,
  type CompositionEvaluationFilter,
  type CompositionExecutionFilter,
  type CompositionSummary,
} from '@/domain/lib/container-composition'
import type {
  CartTreeBranch,
  CartTreeLeaf,
  ContainerSourceTrace,
  PickCartGroup,
} from '@/domain/models/cherryPick'
import type { CartView } from '@/features/tasks/cherry-pick/components/cart-view-switcher'
import { CartTree } from '@/features/tasks/cherry-pick/components/cart-tree'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'
import { CaseSubGroupHeader } from '@/features/testcases/components/case-sub-group-header'
import { ContainerCompositionToolbar } from '@/features/tasks/detail/container-view-switcher'

/** 只读树不消费选择态：空集 + 空操作（不渲染复选框，handler 只为满足必填 props） */
const EMPTY_SELECTION: ReadonlySet<string> = new Set()
const noopLeaf = () => {}
const noopBranch = () => {}
const noopRemove = () => {}
const noopRemoveNode = () => {}
const noopRemoveTask = () => {}

/** 树骨架（信息头 StatBadge 骨架 + 树骨架 3 层，§5.5.3 加载态） */
function CompositionSkeleton() {
  return (
    <div className='flex flex-col gap-2' data-testid='composition-skeleton'>
      {[0, 1, 2].map((row) => (
        <div key={row} className='flex items-center gap-2' style={{ paddingInlineStart: row * 16 }}>
          <Skeleton className='size-3.5 rounded' />
          <Skeleton className='h-4 w-40' />
          <Skeleton className='h-4 w-12' />
        </div>
      ))}
    </div>
  )
}

export function ContainerComposition({
  trace,
  entries,
  summary,
  loading = false,
}: {
  trace: ContainerSourceTrace | null
  /** 全量组成条目（筛选在其上做纯客户端派生） */
  entries: CompositionEntry[]
  summary: CompositionSummary
  loading?: boolean
}) {
  const [view, setView] = useState<CartView>('task')
  const [execution, setExecution] = useState<CompositionExecutionFilter>('all')
  const [evaluation, setEvaluation] = useState<CompositionEvaluationFilter>('all')
  const [onlyMissing, setOnlyMissing] = useState(false)
  const [expandSignal, setExpandSignal] = useState<{ all: boolean; tick: number }>({
    all: false,
    tick: 0,
  })
  // 用例层组织为容器详情会话态，四视图共享（§5.5.3）
  const { org, subView, setOrg, setSubView } = usePickOrg()

  const entryByItemId = useMemo(
    () => new Map(entries.map((e) => [e.itemId, e])),
    [entries]
  )

  /** 筛选（纯客户端；命中叶保留、祖先由重建保留、分支计数按命中集重算） */
  const filtered = useMemo(() => {
    const base = onlyMissing ? filterMissingEntries(entries) : entries
    return filterCompositionEntries(base, execution, evaluation)
  }, [entries, onlyMissing, execution, evaluation])

  const filteredGroups = useMemo(
    () => (filtered.length > 0 ? groupCompositionEntries(filtered) : []),
    [filtered]
  )

  /** 用例视图用例层组织（分组 / 标签 × 平铺 / 交叉） */
  const caseBuckets = useMemo(
    () => (view === 'case' ? organizeCompositionCases(filtered, org, subView) : []),
    [view, filtered, org, subView]
  )

  /** 叶行尾部：源结果 #id + 评估状态 + 源结果时间 + 溯源（§5.5.3 叶行内容） */
  const renderLeafTrailing = (leaf: CartTreeLeaf) => {
    const entry = entryByItemId.get(leaf.entryId)
    if (!entry) return null
    return (
      <>
        <span
          className='text-muted-foreground/70 shrink-0 font-mono text-[10px] tabular-nums'
          title={`源结果 ID ${entry.resultId}`}
        >
          #{entry.resultId}
        </span>
        {entry.evaluated ? (
          <Badge variant='secondary' className='shrink-0 text-[10px]'>
            已评估
          </Badge>
        ) : (
          <Badge
            variant='outline'
            className='text-muted-foreground shrink-0 text-[10px]'
          >
            未评估
          </Badge>
        )}
        {/* 源结果时间：§11-8 的 result_created_at 未落地 → 不渲染（不拿关系行时间顶替，见审计 P2-1） */}
        {entry.resultCreatedAt && (
          <span
            className='text-muted-foreground shrink-0 font-mono text-[10px] whitespace-nowrap tabular-nums'
            title='源结果时间'
          >
            {formatPickDateTime(entry.resultCreatedAt)}
          </span>
        )}
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-6 shrink-0 px-1.5 text-[11px]'
          title={`打开来源任务 #${entry.sourceTaskId}`}
          render={
            <Link to='/tasks/$tab' params={{ tab: String(entry.sourceTaskId) }} />
          }
        >
          溯源
        </Button>
      </>
    )
  }

  /** 分支计数后缀：失败 f / 失效 k（按该节点下过滤后叶统计，§5.5.4） */
  const renderBranchExtra = (branch: CartTreeBranch) => {
    let failed = 0
    let missing = 0
    for (const entryId of branch.entryIds) {
      const entry = entryByItemId.get(entryId)
      if (!entry) continue
      if (entry.executionStatus === 'failed') failed += 1
      if (entry.invalid) missing += 1
    }
    if (failed === 0 && missing === 0) return null
    return (
      <span className='shrink-0 text-[10px] tabular-nums'>
        {failed > 0 && <span className='text-destructive'>· 失败 {failed}</span>}
        {missing > 0 && (
          <span className='text-muted-foreground'> · 失效 {missing}</span>
        )}
      </span>
    )
  }

  const readOnlyTree = (treeGroups: PickCartGroup[], treeView: CartView) => (
    <CartTree
      groups={treeGroups}
      view={treeView}
      readOnly
      selectedEntryIds={EMPTY_SELECTION}
      onToggleLeaf={noopLeaf}
      onToggleBranch={noopBranch}
      onRemoveEntry={noopRemove}
      onRemoveNode={noopRemoveNode}
      onRemoveTask={noopRemoveTask}
      expandSignal={expandSignal}
      renderLeafTrailing={renderLeafTrailing}
      renderBranchExtra={renderBranchExtra}
    />
  )

  const resetFilters = () => {
    setExecution('all')
    setEvaluation('all')
    setOnlyMissing(false)
  }

  const filtersActive =
    execution !== 'all' || evaluation !== 'all' || onlyMissing

  return (
    <section
      id='composition'
      data-testid='container-composition'
      className='bg-card scroll-mt-24 flex flex-col gap-3 rounded-xl border p-4'
    >
      <div className='flex flex-wrap items-center gap-2'>
        <h2 className='text-sm font-medium'>组成</h2>
        <span className='text-muted-foreground text-xs'>
          合并后任务的来源结果结构（只读）
        </span>
        {!loading && summary.total > 0 && (
          <div className='ml-auto flex flex-wrap items-center gap-1.5'>
            <Badge variant='secondary' className='rounded-md px-1.5 text-[11px] tabular-nums'>
              {summary.total} 条结果
            </Badge>
            <Badge variant='outline' className='rounded-md px-1.5 text-[11px] tabular-nums'>
              {summary.caseCount} 个用例
            </Badge>
            <Badge variant='outline' className='rounded-md px-1.5 text-[11px] tabular-nums'>
              {summary.deviceCount} 台设备
            </Badge>
            {summary.failed > 0 && (
              <Badge variant='warning' className='rounded-md px-1.5 text-[11px] tabular-nums'>
                失败 {summary.failed}
              </Badge>
            )}
            {summary.unevaluated > 0 && (
              <Badge variant='outline' className='text-muted-foreground rounded-md px-1.5 text-[11px] tabular-nums'>
                未评估 {summary.unevaluated}
              </Badge>
            )}
          </div>
        )}
      </div>

      {!loading && summary.missing > 0 && (
        <Alert variant='default' className='border-warning/40 bg-warning/10'>
          <AlertTriangle aria-hidden='true' />
          <AlertTitle>
            {summary.missing} 条源结果已失效（源任务或结果已被删除），仅保留溯源记录
          </AlertTitle>
          <AlertDescription>
            <Button
              variant='ghost'
              size='sm'
              className='h-6 px-1.5 text-xs'
              onClick={() => setOnlyMissing((v) => !v)}
            >
              {onlyMissing ? '查看全部结果' : '只看失效'}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {onlyMissing && summary.missing === 0 && (
        <div className='flex items-center gap-2'>
          <Badge variant='outline' className='gap-1 rounded-md px-1.5 text-[11px]'>
            只看失效
            <button type='button' aria-label='退出只看失效' onClick={() => setOnlyMissing(false)}>
              <X aria-hidden='true' className='size-3' />
            </button>
          </Badge>
        </div>
      )}

      <ContainerCompositionToolbar
        view={view}
        onViewChange={setView}
        execution={execution}
        onExecutionChange={setExecution}
        evaluation={evaluation}
        onEvaluationChange={setEvaluation}
        onExpandAll={() => setExpandSignal((s) => ({ all: true, tick: s.tick + 1 }))}
        onCollapseAll={() => setExpandSignal((s) => ({ all: false, tick: s.tick + 1 }))}
        degraded={entries.some((e) => e.statusFromCase || e.evaluationFromCase)}
        org={org}
        subView={subView}
        onOrgChange={setOrg}
        onSubViewChange={setSubView}
      />

      {loading ? (
        <CompositionSkeleton />
      ) : !trace || trace.groups.length === 0 ? (
        <Empty className='rounded-xl border border-dashed py-10'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <ListFilter aria-hidden='true' className='size-4' />
            </EmptyMedia>
            <EmptyTitle>该任务没有合并来源记录</EmptyTitle>
            <EmptyDescription>
              若它是历史合并任务，来源关系可能在合并功能上线前生成
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : filtered.length === 0 ? (
        <Empty className='rounded-xl border border-dashed py-10'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <ListFilter aria-hidden='true' className='size-4' />
            </EmptyMedia>
            <EmptyTitle>无符合筛选条件的来源结果</EmptyTitle>
          </EmptyHeader>
          {filtersActive && (
            <EmptyContent>
              <Button variant='outline' size='sm' onClick={resetFilters}>
                重置筛选
              </Button>
            </EmptyContent>
          )}
        </Empty>
      ) : view === 'case' ? (
        <div className='flex flex-col gap-3'>
          {caseBuckets.map((bucket) => {
            const bucketGroup = {
              key: bucket.key,
              label: bucket.label,
              cases: bucket.units,
              color: bucket.color,
              categoryName: bucket.categoryName,
              totalDuration: 0,
            }
            const muted = bucket.key === '__untagged__' || bucket.key === '__ungrouped__'
            return (
              <div
                key={bucket.key}
                className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'
              >
                <CaseSubGroupHeader group={bucketGroup} muted={muted} />
                <div className='border-t px-2 py-2'>
                  {bucket.subGroups.length > 0 ? (
                    <div className='flex flex-col gap-2'>
                      {bucket.subGroups.map((sub) => (
                        <div key={`${bucket.key}/${sub.key}`} className='flex flex-col gap-1'>
                          <CaseSubGroupHeader
                            group={{
                              key: sub.key,
                              label: sub.label,
                              cases: sub.units,
                              color: sub.color,
                              categoryName: sub.categoryName,
                              totalDuration: 0,
                            }}
                            muted={sub.key === '__untagged__' || sub.key === '__ungrouped__'}
                          />
                          {readOnlyTree(groupCompositionEntries(orgGroupEntries(sub)), 'case')}
                        </div>
                      ))}
                    </div>
                  ) : (
                    readOnlyTree(groupCompositionEntries(orgGroupEntries(bucket)), 'case')
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className='max-h-[560px] overflow-y-auto pr-1'>
          {readOnlyTree(filteredGroups, view)}
        </div>
      )}

      {/* 组成区内出现失败条目是正常业务态（可挑选任务里失败/停止任务均可合并，§5.5.4 解释文案） */}
      {!loading && summary.failed > 0 && (
        <p className='text-muted-foreground/70 text-[11px]'>
          失败条目为正常业务态：执行失败 / 部分失败的任务本身即可被挑选合并。
        </p>
      )}
    </section>
  )
}
