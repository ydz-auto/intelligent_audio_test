/**
 * 候选查询 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2，INT-600）。
 * filters + revision → useQuery；由平铺候选行重建挑选树（§11-3 落地前前端重建）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import type { CherryPickCandidate } from '@/domain/models/cherryPick'
import type {
  PickableTask,
  PickableTaskSortBy,
  PickableTaskSortOrder,
} from '@/domain/models/cherryPick'
import {
  buildPickCaseView,
  buildPickDeviceView,
  buildPickResultTypeView,
  buildPickTree,
} from '@/domain/lib/cherry-pick-tree'
import type { CherryPickFilters } from '@/infrastructure/api/cherry-pick-api'
import {
  fetchAllPickableTasks,
  fetchCandidateFacets,
  fetchCherryPickCandidates,
  fetchPickCaseNames,
  fetchPickableTaskOptions,
} from '@/infrastructure/api/cherry-pick-api'

/** 挑选工作区筛选状态（会话级记忆，§6.4；不持久化） */
export interface PickFilters {
  search?: string
  taskIds: number[]
  deviceIds: number[]
  apiIds: number[]
  resultType: string[]
  executionStatus: string[]
  evaluationStatus: string[]
  timeRange: string
}

export const EMPTY_PICK_FILTERS: PickFilters = {
  taskIds: [],
  deviceIds: [],
  apiIds: [],
  resultType: [],
  executionStatus: [],
  evaluationStatus: [],
  timeRange: 'all',
}

function toApiFilters(filters: PickFilters): CherryPickFilters {
  return {
    search: filters.search || undefined,
    taskIds: filters.taskIds.length > 0 ? filters.taskIds : undefined,
    deviceIds: filters.deviceIds.length > 0 ? filters.deviceIds : undefined,
    apiIds: filters.apiIds.length > 0 ? filters.apiIds : undefined,
    resultType: filters.resultType.length > 0 ? filters.resultType : undefined,
    executionStatus:
      filters.executionStatus.length > 0 ? filters.executionStatus : undefined,
    evaluationStatus:
      filters.evaluationStatus.length > 0 ? filters.evaluationStatus : undefined,
    timeRange: filters.timeRange !== 'all' ? filters.timeRange : undefined,
  }
}

/** 候选查询慢加载阈值（INT-1280）：真实库 3614 行下 candidates 单查 10–45s；
 *  超过阈值仍无数据 → UI 给出可重试提示，替代无限骨架屏。 */
export const SLOW_CANDIDATES_THRESHOLD_MS = 15_000

/** 慢加载探测：fetching 持续超过阈值 → isSlow；restartSlow 重启计时（重试后）；
 *  fetchKey 变化（筛选条件/查询键切换）同样重启计时，避免慢提示跨查询残留。 */
export function useSlowPending(
  fetching: boolean,
  thresholdMs = SLOW_CANDIDATES_THRESHOLD_MS,
  fetchKey?: string
) {
  const [isSlow, setIsSlow] = useState(false)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!fetching) {
      setIsSlow(false)
      return
    }
    setIsSlow(false)
    const timer = window.setTimeout(() => setIsSlow(true), thresholdMs)
    return () => window.clearTimeout(timer)
  }, [fetching, thresholdMs, tick, fetchKey])
  const restartSlow = useCallback(() => setTick((t) => t + 1), [])
  return { isSlow, restartSlow }
}

/** 候选行查询（多条件 AND）；用例名慢路径背景拉取，就绪后二次装饰 caseName（§11-2 降级 → 名称）。
 *  `enabled=false`（挑选向导阶段 1）时不发起——阶段 1 只走 pickable-tasks（INT-1509）。 */
export function useCherryPickCandidates(
  filters: PickFilters,
  options: { enabled?: boolean } = {}
) {
  const enabled = options.enabled ?? true
  const queryClient = useQueryClient()
  // INT-1280：retryNonce 进入查询键——无数据慢查询的 refetch 会被 query-core 去重到在途
  // retryer 而不重发（见 query.fetch「仅已有数据才 cancelRefetch」），重试必须换键生成全新查询。
  const [retryNonce, setRetryNonce] = useState(0)
  const candidatesQueryKey = [
    'cherry-pick',
    'candidates',
    toApiFilters(filters),
    retryNonce,
  ] as const
  const candidatesQuery = useQuery({
    queryKey: candidatesQueryKey,
    queryFn: () => fetchCherryPickCandidates(toApiFilters(filters)),
    staleTime: 15_000,
    enabled,
  })
  const caseNamesQuery = useQuery({
    queryKey: ['cherry-pick', 'case-names'],
    queryFn: fetchPickCaseNames,
    staleTime: 5 * 60_000,
    enabled,
  })
  // INT-1280：候选在途超阈值 → isSlow，UI 给可重试反馈而非无限骨架屏
  const { isSlow, restartSlow } = useSlowPending(
    candidatesQuery.isFetching,
    SLOW_CANDIDATES_THRESHOLD_MS,
    `${JSON.stringify(toApiFilters(filters))}:${retryNonce}`
  )
  const retryCandidates = () => {
    // 中止旧在途请求（避免其继续耗后端聚合），再换 key 强制全新查询重发
    restartSlow()
    void queryClient.cancelQueries({ queryKey: candidatesQueryKey })
    setRetryNonce((n) => n + 1)
  }
  const data = useMemo(() => {
    let rows = candidatesQuery.data
    const caseNames = caseNamesQuery.data
    if (rows && caseNames) {
      // 仅补未装饰的候选行（缺名降级显示用例 ID → 名称）
      rows = rows.map((c) =>
        c.caseName ? c : { ...c, caseName: caseNames.get(c.caseId) ?? null }
      )
    }
    // search 命中用例名/用例 ID/任务名（用例名装饰就绪后生效）
    if (rows && filters.search && filters.search.trim()) {
      const kw = filters.search.trim().toLowerCase()
      rows = rows.filter(
        (c) =>
          (c.caseName ?? '').toLowerCase().includes(kw) ||
          c.caseId.toLowerCase().includes(kw) ||
          c.taskName.toLowerCase().includes(kw)
      )
    }
    return rows
  }, [candidatesQuery.data, caseNamesQuery.data, filters.search])
  return { ...candidatesQuery, data, isSlow, retryCandidates }
}

/** 阶段 1 可挑选任务清单（INT-1496 `GET /tasks/cherry-picks/pickable-tasks`）。
 *  服务端排序（sort_by/sort_order）取代客户端状态权重排序；按 per_page 拉齐分页，
 *  使「全选当前筛选」覆盖 total 全部任务，不出现只选到首页。 */
export function usePickableTasks(params: {
  sortBy: PickableTaskSortBy
  sortOrder: PickableTaskSortOrder
}) {
  const queryClient = useQueryClient()
  const [retryNonce, setRetryNonce] = useState(0)
  const queryKey = [
    'cherry-pick',
    'pickable-tasks',
    params.sortBy,
    params.sortOrder,
    retryNonce,
  ] as const
  const query = useQuery({
    queryKey,
    queryFn: () =>
      fetchAllPickableTasks({ sortBy: params.sortBy, sortOrder: params.sortOrder }),
    staleTime: 30_000,
  })
  const { isSlow, restartSlow } = useSlowPending(
    query.isFetching,
    SLOW_CANDIDATES_THRESHOLD_MS,
    `${params.sortBy}:${params.sortOrder}:${retryNonce}`
  )
  const retry = () => {
    restartSlow()
    void queryClient.cancelQueries({ queryKey })
    setRetryNonce((n) => n + 1)
  }
  return {
    items: (query.data?.items ?? []) as PickableTask[],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    isError: query.isError,
    isSlow,
    retry,
  }
}

/** 筛选器选项（来源任务/设备/结果类型，动态选项数据源 §3.4）。
 *  来源任务与阶段 1 清单同源（pickable-tasks）；设备/结果类型仍由阶段 2
 *  candidates facet 提供（一次查询同时出两类选项，§11-3 降级不在本卡范围）。
 *  `enabled=false`（阶段 1）时整组不发起——阶段 1 只允许打一条 pickable-tasks。 */
export function usePickFilterOptions(enabled = true) {
  const tasks = useQuery({
    queryKey: ['cherry-pick', 'options', 'tasks'],
    queryFn: fetchPickableTaskOptions,
    staleTime: 60_000,
    enabled,
  })
  const facets = useQuery({
    queryKey: ['cherry-pick', 'options', 'facets'],
    queryFn: fetchCandidateFacets,
    staleTime: 60_000,
    enabled,
  })
  return {
    tasks: tasks.data ?? [],
    devices: facets.data?.devices ?? [],
    resultTypes: facets.data?.resultTypes ?? [],
  }
}

/** 挑选树（候选行重建，R10 已加购标记来自购物车 resultIdSet） */
export function useCherryPickTree(candidates: CherryPickCandidate[] | undefined) {
  const resultIdSet = usePickCartStore((s) => s.resultIdSet)
  return useMemo(
    () => buildPickTree(candidates ?? [], resultIdSet),
    [candidates, resultIdSet]
  )
}

/** 用例视图树（§3.8.3：用例→设备/API→result_type→结果行；与设备/结果类型视图共享 selectedResultIds） */
export function useCherryPickCaseView(candidates: CherryPickCandidate[] | undefined) {
  const resultIdSet = usePickCartStore((s) => s.resultIdSet)
  return useMemo(
    () => buildPickCaseView(candidates ?? [], resultIdSet),
    [candidates, resultIdSet]
  )
}

/** 设备视图树（§3.8.3：设备/API→result_type→用例→结果行，新增） */
export function useCherryPickDeviceView(candidates: CherryPickCandidate[] | undefined) {
  const resultIdSet = usePickCartStore((s) => s.resultIdSet)
  return useMemo(
    () => buildPickDeviceView(candidates ?? [], resultIdSet),
    [candidates, resultIdSet]
  )
}

/** 结果类型视图树（§3.8.3：result_type→设备/API→用例→结果行，新增） */
export function useCherryPickResultTypeView(candidates: CherryPickCandidate[] | undefined) {
  const resultIdSet = usePickCartStore((s) => s.resultIdSet)
  return useMemo(
    () => buildPickResultTypeView(candidates ?? [], resultIdSet),
    [candidates, resultIdSet]
  )
}
