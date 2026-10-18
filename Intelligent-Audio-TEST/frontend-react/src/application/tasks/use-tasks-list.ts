/**
 * 任务域列表 query（application 层，09_任务域.md §3.2 URL 态 → queryKey）。
 * 日常/已发布共用同一 useQuery 骨架：tab + search + 各页签专属筛选 + 分页 进 queryKey。
 * 「挑选合并」页签列表由 features/tasks/cherry-pick/index.tsx 自持
 * （统一容器列表 merged ∪ cherry_pick，§11-1；本 hook 不再承载）。
 * mock 桩见 infrastructure/api/tasks-list-api.ts（接线后仅替换桩实现）。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchPublishedTaskList,
  fetchTaskList,
} from '@/infrastructure/api/tasks-list-api'
import type { TasksTabKey } from '@/features/tasks/constants'

export interface TaskListFilters {
  search?: string
  executionStatus?: string | null
  evaluationStatus?: string | null
  tags?: string[]
  timeRange?: string
  type?: string | null
  ptStatus?: string | null
  mergeStatus?: string | null
  favorite?: boolean
  trash?: boolean
  algorithmType?: string | null
  /** 分页（§3.11 URL 化分页：page/pageSize 进 search，接线后随 useTableUrlState） */
  page?: number
  pageSize?: number
}

/** 时间范围 → 后端 start_date/end_date（照旧 Vue useTaskList 口径：今日/昨日/近7天/近30天） */
export function timeRangeToDateBounds(
  timeRange: string | undefined
): { startDate?: string; endDate?: string } {
  if (!timeRange || timeRange === 'all') return {}
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  switch (timeRange) {
    case 'today':
      return { startDate: today.toISOString() }
    case 'yesterday': {
      const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
      return { startDate: yesterday.toISOString(), endDate: today.toISOString() }
    }
    case 'week':
      return { startDate: new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString() }
    case 'month':
      return { startDate: new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString() }
    default:
      return {}
  }
}

/** 全局算法联动（INT-344 Zustand；非空时请求自动附 algorithm_type） */
export function useTasksList(tab: TasksTabKey, filters: TaskListFilters) {
  const queryKey = ['tasks', tab, filters] as const

  return useQuery({
    queryKey,
    queryFn: async () => {
      switch (tab) {
        case 'published':
          return fetchPublishedTaskList({
            page: filters.page,
            perPage: filters.pageSize,
            search: filters.search,
            type: filters.type,
            ptStatus: filters.ptStatus,
          })
        case 'cherry-picks':
          // 统一容器列表由 CherryPickTab 自持（§11-1 客户端双查询合并）
          return { items: [], total: 0 }
        case 'daily':
        default:
          return fetchTaskList({
            page: filters.page,
            perPage: filters.pageSize,
            search: filters.search,
            executionStatus: filters.executionStatus,
            evaluationStatus: filters.evaluationStatus,
            tags: filters.tags,
            favorite: filters.favorite,
            trash: filters.trash,
            algorithmType: filters.algorithmType,
            ...timeRangeToDateBounds(filters.timeRange),
          })
      }
    },
    staleTime: 15_000,
  })
}
