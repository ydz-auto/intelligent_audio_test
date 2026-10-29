/**
 * 候选树 / 叶明细 / 全量选择 hook（application/tasks/cherry-pick，INT-1510 §8.2 接线）。
 *
 * 阶段 2 数据源（唯一口径，不保留降级开关）：
 *   - 树骨架与节点计数 ← GET /tasks/cherry-picks/candidates/tree（`meta` 供命名与元信息）
 *   - 叶明细分页       ← GET /tasks/cherry-picks/candidates（按展开节点的过滤组合，服务端分页）
 *   - 全选当前筛选     ← POST /tasks/cherry-picks/candidates/select-all（跨页，服务端集合）
 * 三视图展示口径沿用 INT-1694（任务末级 / 用例层组织 / 用例卡），见 pick-candidate-tree.ts。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import type {
  PickableTask,
  PickableTaskSortBy,
  PickableTaskSortOrder,
  PickCandidateTree,
  PickLeafFilter,
} from '@/domain/models/cherryPick'
import {
  buildPickCaseView,
  buildPickDeviceView,
  buildPickResultTypeView,
  buildPickTaskTree,
  buildPickTaskView,
  buildResultIndex,
  buildLeafFilterKey,
  isPendingResultType,
  PENDING_RESULT_TYPE_VALUE,
  resultTypeLabel,
  treeResultTypeVariety,
  type PickTaskSubView,
} from '@/domain/lib/pick-candidate-tree'
import type { CherryPickTreeParams } from '@/infrastructure/api/cherry-pick-api'
import type {
  PickOrgDimension,
  PickSubView,
} from '@/application/tasks/cherry-pick/use-pick-org'
import {
  fetchAllPickableTasks,
  fetchCherryPickCandidatePage,
  fetchCherryPickCandidateTree,
  fetchPickableTaskOptions,
  fetchSelectAllCandidates,
  type CherryPickCandidatePage,
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

/** 筛选状态 → 服务端参数（树与全选同一口径，全部服务端过滤） */
export function toTreeParams(filters: PickFilters): CherryPickTreeParams {
  return {
    taskIds: filters.taskIds,
    deviceIds: filters.deviceIds.length > 0 ? filters.deviceIds : undefined,
    apiIds: filters.apiIds.length > 0 ? filters.apiIds : undefined,
    caseKeyword: filters.search || undefined,
    resultType: filters.resultType.length > 0 ? filters.resultType[0] : undefined,
    executionStatus:
      filters.executionStatus.length > 0 ? filters.executionStatus : undefined,
    evaluationStatus:
      filters.evaluationStatus.length > 0 ? filters.evaluationStatus : undefined,
    timeRange: filters.timeRange !== 'all' ? filters.timeRange : undefined,
  }
}

/** 候选查询慢加载阈值（INT-1280）：超过阈值仍无数据 → UI 给可重试提示，替代无限骨架屏。 */
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

/* ============================================================
 * 阶段 2 候选树（唯一树骨架数据源）
 * ============================================================ */

/** 阶段 2 候选树查询（`enabled=false`（阶段 1）时不发起——阶段 1 只走 pickable-tasks）。
 *  `placeholderData: keepPreviousData`：切换筛选时保留上一棵树，不闪空树（§8.2 第 8 条）。 */
export function useCherryPickCandidateTree(
  filters: PickFilters,
  options: { enabled?: boolean } = {}
) {
  const enabled = options.enabled ?? true
  const queryClient = useQueryClient()
  const params = useMemo(() => toTreeParams(filters), [filters])
  // task_ids 必填 1–200：阶段 1 尚未选任务时不发请求
  const canQuery = enabled && params.taskIds.length > 0
  // INT-1280：retryNonce 进入查询键——无数据慢查询的 refetch 会被 query-core 去重到在途
  // retryer 而不重发，重试必须换键生成全新查询。
  const [retryNonce, setRetryNonce] = useState(0)
  const queryKey = [
    'cherry-pick',
    'candidate-tree',
    params,
    retryNonce,
  ] as const
  const query = useQuery({
    queryKey,
    queryFn: () => fetchCherryPickCandidateTree(params),
    staleTime: 15_000,
    enabled: canQuery,
    placeholderData: keepPreviousData,
  })
  const { isSlow, restartSlow } = useSlowPending(
    query.isFetching,
    SLOW_CANDIDATES_THRESHOLD_MS,
    `${JSON.stringify(params)}:${retryNonce}`
  )
  const retryTree = () => {
    // 中止旧在途请求（避免其继续耗后端聚合），再换 key 强制全新查询重发
    restartSlow()
    void queryClient.cancelQueries({ queryKey })
    setRetryNonce((n) => n + 1)
  }
  return { ...query, params, data: query.data, isSlow, retryTree }
}

/** 候选树 → 三视图树 + 任务视角树 + 结果归属索引（组件只消费，不重算） */
export function usePickTrees(
  data: PickCandidateTree | undefined,
  org: PickOrgDimension = 'group',
  subView: PickSubView = 'flat',
  taskSubView: PickTaskSubView = 'case'
) {
  return useMemo(
    () => ({
      total: data?.total ?? 0,
      taskCount: data?.taskCount ?? 0,
      taskTree: buildPickTaskTree(data),
      caseView: buildPickCaseView(data),
      deviceView: buildPickDeviceView(data, org, subView),
      resultTypeView: buildPickResultTypeView(data, org, subView),
      /** 任务视图（B 组：任务首级 + 三子模式） */
      taskView: buildPickTaskView(data, taskSubView, org, subView),
      resultTypeVariety: treeResultTypeVariety(data),
      index: buildResultIndex(data),
    }),
    [data, org, subView, taskSubView]
  )
}

/** 叶明细分页页大小（服务端 per_page 上限 200；节点内翻页 20 行便于对齐树行密度） */
export const LEAF_PAGE_SIZE = 20

/** 阶段 2 叶明细分页（展开的节点按 task_ids + case_ids + device_id/api_id + result_type 查）。
 *  名称直接取候选行 DTO（后端已返 case_name/device_name/api_name），不再另查列表补名。 */
export function usePickLeafPage(
  filter: PickLeafFilter | null,
  page: number,
  options: { enabled?: boolean } = {}
) {
  const enabled = options.enabled ?? true
  const key = filter ? buildLeafFilterKey(filter) : ''
  return useQuery<CherryPickCandidatePage>({
    queryKey: ['cherry-pick', 'node-leaves', key, page],
    queryFn: () => fetchCherryPickCandidatePage(filter!, page, LEAF_PAGE_SIZE),
    enabled: enabled && filter != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}

/** 全选当前筛选（服务端跨页集合，§8.2.5 第 3 条）：提交中禁重复（§8.2 第 7 条） */
export function useSelectAllCandidates(filters: PickFilters) {
  const params = useMemo(() => toTreeParams(filters), [filters])
  return useMutation({
    mutationFn: () => fetchSelectAllCandidates(params),
  })
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

/** 筛选器选项：来源任务同源 pickable-tasks；设备 / API / 结果类型一律从候选树
 *  `meta.devices` / `meta.apis` / 树内 result_type 派生（不再由已加载行推断，§8.2 第 2 条）。
 *  `enabled=false`（阶段 1）时整组不发起——阶段 1 只允许打一条 pickable-tasks。 */
export function usePickFilterOptions(
  enabled: boolean,
  tree: PickCandidateTree | undefined
) {
  const tasks = useQuery({
    queryKey: ['cherry-pick', 'options', 'tasks'],
    queryFn: fetchPickableTaskOptions,
    staleTime: 60_000,
    enabled,
  })
  const devices = useMemo(
    () =>
      (tree?.meta.devices ?? []).map((d) => ({
        id: d.deviceId,
        name: d.deviceName?.trim() || `设备 ${d.deviceId}`,
      })),
    [tree]
  )
  const apis = useMemo(
    () =>
      (tree?.meta.apis ?? []).map((a) => ({
        id: a.apiId,
        name: a.apiName?.trim() || `API ${a.apiId}`,
      })),
    [tree]
  )
  const resultTypes = useMemo(() => {
    const values = new Set<string>()
    for (const taskNode of tree?.tree ?? []) {
      for (const caseNode of taskNode.cases) {
        for (const deviceNode of caseNode.devices) {
          for (const rtNode of deviceNode.resultTypes) {
            values.add(
              isPendingResultType(rtNode.resultType)
                ? PENDING_RESULT_TYPE_VALUE
                : rtNode.resultType.trim()
            )
          }
        }
      }
    }
    return [...values].map((value) => ({ value, label: resultTypeLabel(value) }))
  }, [tree])
  return {
    tasks: tasks.data ?? [],
    devices,
    apis,
    resultTypes,
  }
}
