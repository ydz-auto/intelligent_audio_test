/**
 * 分组内用例懒加载 query（application 层；INT-1284 分组视图修复）。
 * 分组卡按 /groups 全量渲染（计数取 test_case_count），组内用例在展开时按分组懒加载：
 * useInfiniteQuery 每页 GROUP_CASE_PAGE_SIZE 条（真实库栈 /testcases 单页响应随条数超线性变慢，
 * 小页 + 服务端翻页比一次拉全量/单页 100 快一个数量级），「加载更多」翻下一页。
 * queryKey 前缀 testcase-group-cases 独立于 ['testcases']（列表/批量缓存），
 * 避免 useIsFetching(['testcases']) 在分组展开取数时误降列表透明度、以及
 * setQueriesData(['testcases']) 就地回写收藏时把无限查询误当列表更新。
 * 筛选变化（搜索/标签/维度/算法/收藏/回收站）进 queryKey → 展开组时按新筛选重拉。
 */
import { useInfiniteQuery } from '@tanstack/react-query'

import { fetchTestCases } from '@/infrastructure/api/testcases-api'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'

/** 分组内懒加载每页条数（INT-1284：后端单页响应随条数超线性变慢，取 20 页平衡往返与体积） */
const GROUP_CASE_PAGE_SIZE = 20

export function useGroupTestCases(
  groupId: string,
  filters: TestCaseListFilters,
  /** 空分组（test_case_count=0）不发起请求；展开时置 true 由挂载态触发取数 */
  enabled = true
) {
  return useInfiniteQuery({
    queryKey: ['testcase-group-cases', groupId, filters] as const,
    queryFn: ({ pageParam }) =>
      fetchTestCases({
        ...filters,
        groupId,
        page: pageParam,
        perPage: GROUP_CASE_PAGE_SIZE,
      }),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      if (last.items.length === 0) return undefined
      const next = (last.page ?? 1) + 1
      if (last.pages != null && next > last.pages) return undefined
      return next
    },
    enabled,
    staleTime: 15_000,
  })
}
