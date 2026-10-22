/**
 * 组内用例懒加载 query（application 层，INT-1267 分组视图修复）。
 * 分组卡头计数以 /groups testCaseCount 为准（与旧 Vue getGroupTotalCount 对位）；
 * 组内用例展开时才按 group_id 懒拉（Vue testCaseStore.fetchCasesByGroup 对位），
 * 每页 GROUP_PAGE_SIZE 条、「加载更多」页续并累加去重；筛选/分组变化时页号与列表复位。
 * queryKey 挂 ['testcases', 'by-group-inline', ...]：消费方 invalidateQueries(['testcases'])
 * 与 useIsFetching(['testcases']) 降透明度均覆盖到（与整表重拉同源，组内增删后列表一致）。
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import {
  GROUP_PAGE_SIZE,
  fetchTestCasesByGroup,
} from '@/infrastructure/api/testcases-api'

export function useGroupCases(
  groupId: string,
  filters: TestCaseListFilters,
  enabled: boolean
) {
  const [page, setPage] = useState(1)
  /** 已累加的组内用例（跨页合并去重；页续时不被当前页数据替换） */
  const [items, setItems] = useState<TestCaseListItem[]>([])
  const [total, setTotal] = useState(0)
  const filtersKey = JSON.stringify(filters)

  // 筛选条件变化（搜索/分组/标签/维度/算法/收藏/回收站）或切换分组 → 页号与列表复位
  useEffect(() => {
    setPage(1)
    setItems([])
    setTotal(0)
  }, [filtersKey, groupId])

  const query = useQuery({
    queryKey: ['testcases', 'by-group-inline', groupId, filtersKey, page],
    queryFn: () => fetchTestCasesByGroup(groupId, filters, page, GROUP_PAGE_SIZE),
    enabled,
    staleTime: 15_000,
  })

  // 页数据到达：首页替换，后续页追加去重（同页重拉不产生重复卡）
  useEffect(() => {
    if (!query.data) return
    setTotal(query.data.total)
    setItems((prev) => {
      if (page === 1) return query.data.items
      const ids = new Set(prev.map((c) => c.id))
      return [...prev, ...query.data.items.filter((c) => !ids.has(c.id))]
    })
  }, [query.data, page])

  return {
    items,
    total,
    hasMore: total > page * GROUP_PAGE_SIZE,
    /** 本组首次加载中（尚无已累加数据）——展开空组显示加载骨架 */
    isLoading: query.isLoading && items.length === 0,
    isFetching: query.isFetching,
    loadMore: () => setPage((p) => p + 1),
  }
}
