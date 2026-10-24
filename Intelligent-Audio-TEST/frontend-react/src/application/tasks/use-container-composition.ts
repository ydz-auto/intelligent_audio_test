/**
 * 容器组成数据装配（18_挑选合并功能交互重设计.md §5.5.3 / §5.5.8，INT-1711）。
 * `useQuery(['task', id, 'cherry-pick-source'])` 拉 source 端点（非容器 / 5xx / 网络均归一 null）；
 * 与详情 query（`['tasks','detail',id]`，详情页四卡本来就在）join 后 `useMemo` 派生组成条目与摘要。
 * 同一 hook 供落点 ② 容器详情组成区与落点 ③ 页签行展开复用：react-query 以 taskId 为 key
 * 天然按任务缓存，再次展开命中缓存、收起不释放、不重复请求。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { useTaskDetail } from '@/application/tasks/use-task-detail'
import {
  groupCompositionEntries,
  summarizeComposition,
  toCompositionEntries,
  type CompositionEntry,
  type CompositionSummary,
} from '@/domain/lib/container-composition'
import type { ContainerSourceTrace, PickCartGroup } from '@/domain/models/cherryPick'
import { fetchContainerSourceTrace } from '@/infrastructure/api/cherry-pick-api'

export interface ContainerCompositionModel {
  /** 200（groups 可为空）→ 挑选合并容器；null（任意 ApiError）→ 非容器，静默不渲染 */
  isContainer: boolean
  isLoading: boolean
  trace: ContainerSourceTrace | null
  entries: CompositionEntry[]
  /** 按来源任务分组（与购物车 PickCartGroup 同构，喂 CartTree / 三视图） */
  groups: PickCartGroup[]
  summary: CompositionSummary
  /** 任一叶行执行状态 / 评估状态取自降级用例行（工具行一次性提示，§5.5.4） */
  statusDegraded: boolean
  /** 详情 query 仍在加载（落点 ③ 首次展开补拉的那一次，§5.5.3） */
  detailLoading: boolean
  /** 详情 query 失败（§5.5.6「页签行展开补拉详情失败」→ Empty + 重试） */
  detailError: boolean
  /** 详情 + 溯源一起重拉（落点 ③ Empty 的「重试」） */
  retry: () => void
}

const EMPTY_GROUPS: PickCartGroup[] = []
const EMPTY_SUMMARY: CompositionSummary = {
  total: 0,
  failed: 0,
  unevaluated: 0,
  missing: 0,
  taskCount: 0,
  caseCount: 0,
  deviceCount: 0,
}

export function useContainerComposition(
  taskId: number,
  options: { enabled?: boolean } = {}
): ContainerCompositionModel {
  const { enabled = true } = options
  // 详情 query（详情页已有同一 key → 与四卡共用，不产生额外请求；行展开落点复用时按需拉一次）
  const detailQuery = useTaskDetail(taskId, enabled)
  const sourceQuery = useQuery({
    queryKey: ['task', taskId, 'cherry-pick-source'],
    queryFn: () => fetchContainerSourceTrace(taskId),
    // 非容器是常态（实测 400 / code:203），不做重试，避免每个普通任务详情页重复请求
    retry: false,
    staleTime: 60_000,
    enabled,
  })

  const detail = detailQuery.data
  const trace = sourceQuery.data ?? null

  const entries = useMemo(
    () =>
      toCompositionEntries(
        trace,
        detail?.cases ?? [],
        detail?.devices ?? [],
        detail?.apis ?? []
      ),
    [trace, detail]
  )

  const groups = useMemo(
    () => (entries.length > 0 ? groupCompositionEntries(entries) : EMPTY_GROUPS),
    [entries]
  )

  const summary = useMemo(
    () => (entries.length > 0 ? summarizeComposition(entries) : EMPTY_SUMMARY),
    [entries]
  )

  return {
    isContainer: trace != null,
    isLoading: sourceQuery.isLoading,
    trace,
    entries,
    groups,
    summary,
    statusDegraded: entries.some((e) => e.statusFromCase || e.evaluationFromCase),
    detailLoading: detailQuery.isLoading,
    detailError: detailQuery.isError,
    retry: () => {
      if (detailQuery.isError) void detailQuery.refetch()
      if (sourceQuery.data == null) void sourceQuery.refetch()
    },
  }
}
