/**
 * 分组视图「筛选命中」聚合（INT-2154，application 层）。
 *
 * 背景：分组卡计数取自 /groups 的 testCaseCount（分组全量，不随搜索变化），分组视图的
 * 组内用例虽按筛选懒加载，但组头计数与分组集合都不动——搜索命中的分组若排在分页第一屏
 * 之外（按数量降序），界面看起来「搜索没生效」。本 hook 按当前筛选把命中用例全量取回
 * 按 groupId 聚合，供分组视图显示「命中 N 条」、隐藏零命中分组、按命中数排序。
 *
 * 仅在搜索词非空且未锁定单个分组时启用（其余筛选态分组集合不变，不做额外请求）；
 * queryKey 挂 ['testcases', ...] 前缀：用例增删改后的 invalidateQueries(['testcases']) 同源刷新。
 */
import { useQuery } from '@tanstack/react-query'

import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import { UNGROUPED_GROUP_ID } from '@/features/testcases/constants'
import { fetchAllTestCasesByFilter } from '@/infrastructure/api/testcases-api'

export interface CaseGroupHits {
  /** 搜索命中聚合是否生效（搜索词非空、未锁定单分组、且统计成功） */
  active: boolean
  /** groupId → 命中用例数（含未分组哨兵）；未生效/加载中为 null */
  counts: Map<string, number> | null
  /** 命中用例总数 */
  total: number
  /** 每个有命中的分组数 */
  groupCount: number
  isLoading: boolean
  /** 统计失败（调用方回落到「分组全量」展示，不隐藏任何分组） */
  isError: boolean
}

export function useCaseGroupHits(filters: TestCaseListFilters): CaseGroupHits {
  const keyword = filters.search?.trim() ?? ''
  /** 锁定单个分组时分组集合已由 groupId 收窄，无需按命中重排/隐藏 */
  const active = keyword !== '' && !filters.groupId

  const query = useQuery({
    queryKey: [
      'testcases',
      'group-hits',
      keyword,
      filters.tag ?? null,
      filters.dimensionId ?? null,
      filters.algorithmType ?? null,
      filters.favorite ?? false,
      filters.trash ?? false,
    ],
    queryFn: async () => {
      const cases = await fetchAllTestCasesByFilter({
        search: keyword,
        tag: filters.tag,
        dimensionId: filters.dimensionId,
        algorithmType: filters.algorithmType,
        favorite: filters.favorite,
        trash: filters.trash,
      })
      const counts = new Map<string, number>()
      for (const item of cases) {
        const key = item.groupId ?? UNGROUPED_GROUP_ID
        counts.set(key, (counts.get(key) ?? 0) + 1)
      }
      return { counts, total: cases.length }
    },
    enabled: active,
    staleTime: 15_000,
  })

  return {
    active: active && !query.isError,
    counts: query.data?.counts ?? null,
    total: query.data?.total ?? 0,
    groupCount: query.data?.counts.size ?? 0,
    isLoading: active && query.isLoading,
    isError: active && query.isError,
  }
}
