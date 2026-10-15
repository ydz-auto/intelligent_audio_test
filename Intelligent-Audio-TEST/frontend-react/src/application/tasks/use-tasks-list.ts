/**
 * 任务域列表 query（application 层，09_任务域.md §3.2 URL 态 → queryKey）。
 * 四页签共用同一 useQuery 骨架：tab + search + 各页签专属筛选 进 queryKey。
 * mock 桩见 infrastructure/api/tasks-list-api.ts（接线后仅替换桩实现）。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchCherryPickList,
  fetchMergedTaskList,
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
            search: filters.search,
            type: filters.type,
            ptStatus: filters.ptStatus,
          })
        case 'merged':
          return fetchMergedTaskList({ search: filters.search })
        case 'cherry-picks':
          return fetchCherryPickList({ search: filters.search })
        case 'daily':
        default:
          return fetchTaskList({
            search: filters.search,
            executionStatus: filters.executionStatus,
            evaluationStatus: filters.evaluationStatus,
            tags: filters.tags,
            favorite: filters.favorite,
            trash: filters.trash,
            algorithmType: filters.algorithmType,
          })
      }
    },
    staleTime: 15_000,
  })
}
