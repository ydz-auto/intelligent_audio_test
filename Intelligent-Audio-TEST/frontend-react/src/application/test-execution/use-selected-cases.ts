/**
 * 步骤一「只显示已选中」数据源（application 层；10_测试执行.md §3.5 选择态复核）。
 *
 * 分组视图的组内用例来自按分组懒加载分页、标签视图只聚合当前列表页，两者都拿不到
 * 「已勾选但尚未加载」的用例行；而选择集只有 id（全选结果/反选由 POST /testcases/ids
 * 服务端圈定）。因此开关打开时按**当前筛选**经列表端点逐页取全量用例行，再与已选 id 求交，
 * 得到完整、可渲染的已选用例集（与 useCaseGroupHits 同一翻页口径）。
 *
 * queryKey 挂 ['testcases', ...] 前缀：用例增删改后 invalidateQueries(['testcases']) 同源刷新。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import type { TestCaseListItem } from '@/domain/models/testCase'
import { fetchAllTestCasesByFilter } from '@/infrastructure/api/testcases-api'

export interface SelectedCasesResult {
  /** 当前筛选下已勾选的用例行（保持列表端点返回顺序） */
  cases: TestCaseListItem[]
  isLoading: boolean
  /** 全量取数失败（调用方给错误态 + 重试，不伪装成「没有已选用例」） */
  isError: boolean
  refetch: () => void
}

export function useSelectedCases(
  enabled: boolean,
  filters: TestCaseListFilters,
  selectedIds: string[]
): SelectedCasesResult {
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const active = enabled && selectedIds.length > 0

  const query = useQuery({
    queryKey: [
      'testcases',
      'selected-only',
      filters.search?.trim() ?? '',
      filters.groupId ?? null,
      filters.tag ?? null,
      filters.dimensionId ?? null,
      filters.algorithmType ?? null,
      filters.favorite ?? false,
      filters.trash ?? false,
    ],
    queryFn: () =>
      fetchAllTestCasesByFilter({
        search: filters.search,
        groupId: filters.groupId,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        algorithmType: filters.algorithmType,
        favorite: filters.favorite,
        trash: filters.trash,
      }),
    enabled: active,
    staleTime: 15_000,
  })

  const cases = useMemo(
    () => (query.data ?? []).filter((c) => selectedIdSet.has(c.id)),
    [query.data, selectedIdSet]
  )

  return {
    cases,
    isLoading: active && query.isLoading,
    isError: active && query.isError,
    refetch: () => void query.refetch(),
  }
}
