/**
 * 用例列表 query（application 层，11_用例域.md §3.2 URL 态 → queryKey）。
 * view=by-group / by-tag 分派两个数据源（后端 view=tag 契约保留，前端拍平为行集合）；
 * 搜索/类型/分组/标签/评估维度/收藏/回收站/全局算法全部进 queryKey。
 * mock 桩见 infrastructure/api/testcases-api.ts（接线后仅替换桩实现）。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchGroupedTestCases,
  fetchTagGroupedTestCases,
  type TestCaseListQuery,
} from '@/infrastructure/api/testcases-api'
import type { TestCasesViewKey } from '@/features/testcases/constants'

export interface TestCaseListFilters {
  search?: string
  groupId?: string | null
  /** 标签筛选（INT-592 单选：后端 tag 参数为单值，Tag.name == tag SQL join） */
  tag?: string | null
  dimensionId?: number | null
  favorite?: boolean
  trash?: boolean
  /** 全局算法联动（INT-344 Zustand；非空时请求自动附 algorithm_type） */
  algorithmType?: string | null
}

/** 用例列表（双视图共用骨架；mock 阶段不服务端分页） */
export function useTestCasesList(
  view: TestCasesViewKey,
  filters: TestCaseListFilters
) {
  const queryKey = ['testcases', view, filters] as const

  return useQuery({
    queryKey,
    queryFn: async () => {
      const query: TestCaseListQuery = {
        search: filters.search,
        groupId: filters.groupId,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        favorite: filters.favorite,
        trash: filters.trash,
        algorithmType: filters.algorithmType,
        view,
      }
      if (view === 'by-tag') return fetchTagGroupedTestCases(query)
      return fetchGroupedTestCases(query)
    },
    staleTime: 15_000,
    // 筛选/视图切换时保留上一页数据，表格降透明度不消失（users 同款）
    placeholderData: (prev) => prev,
  })
}
