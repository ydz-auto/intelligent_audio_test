/**
 * 候选查询 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2，INT-600）。
 * filters + revision → useQuery；由平铺候选行重建挑选树（§11-3 落地前前端重建）。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import type { CherryPickCandidate } from '@/domain/models/cherryPick'
import { buildPickTree } from '@/domain/lib/cherry-pick-tree'
import type { CherryPickFilters } from '@/infrastructure/api/cherry-pick-api'
import {
  fetchCherryPickCandidates,
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

/** 候选行查询（多条件 AND） */
export function useCherryPickCandidates(filters: PickFilters) {
  return useQuery({
    queryKey: ['cherry-pick', 'candidates', toApiFilters(filters)],
    queryFn: () => fetchCherryPickCandidates(toApiFilters(filters)),
    staleTime: 15_000,
  })
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
