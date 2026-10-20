/**
 * 候选查询 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2，INT-600）。
 * filters + revision → useQuery；由平铺候选行重建挑选树（§11-3 落地前前端重建）。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import type { CherryPickCandidate } from '@/domain/models/cherryPick'
import {
  buildPickCaseView,
  buildPickDeviceView,
  buildPickResultTypeView,
  buildPickTree,
} from '@/domain/lib/cherry-pick-tree'
import type { CherryPickFilters } from '@/infrastructure/api/cherry-pick-api'
import {
  fetchCherryPickCandidates,
  fetchPickCaseNames,
  fetchPickableDevices,
  fetchPickableTasks,
  fetchResultTypeOptions,
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

/** 候选行查询（多条件 AND）；用例名慢路径背景拉取，就绪后二次装饰 caseName（§11-2 降级 → 名称） */
export function useCherryPickCandidates(filters: PickFilters) {
  const candidatesQuery = useQuery({
    queryKey: ['cherry-pick', 'candidates', toApiFilters(filters)],
    queryFn: () => fetchCherryPickCandidates(toApiFilters(filters)),
    staleTime: 15_000,
  })
  const caseNamesQuery = useQuery({
    queryKey: ['cherry-pick', 'case-names'],
    queryFn: fetchPickCaseNames,
    staleTime: 5 * 60_000,
  })
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
  return { ...candidatesQuery, data }
}

/** 筛选器选项（来源任务/设备/结果类型，动态选项数据源 §3.4） */
export function usePickFilterOptions() {
  const tasks = useQuery({
    queryKey: ['cherry-pick', 'options', 'tasks'],
    queryFn: fetchPickableTasks,
    staleTime: 60_000,
  })
  const devices = useQuery({
    queryKey: ['cherry-pick', 'options', 'devices'],
    queryFn: fetchPickableDevices,
    staleTime: 60_000,
  })
  const resultTypes = useQuery({
    queryKey: ['cherry-pick', 'options', 'result-types'],
    queryFn: fetchResultTypeOptions,
    staleTime: 60_000,
  })
  return {
    tasks: tasks.data ?? [],
    devices: devices.data ?? [],
    resultTypes: resultTypes.data ?? [],
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
