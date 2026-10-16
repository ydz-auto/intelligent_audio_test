/**
 * 用例分组 query（application 层，11_用例域.md §3.5）。
 * 分组 facet 选项 + 分组头行渲染共用同一 queryKey ['testcase-groups']；
 * 分组 CRUD 后 invalidate 联动（mock 态动作走 toast 演示）。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchGroups } from '@/infrastructure/api/groups-api'

export function useCaseGroups() {
  return useQuery({
    queryKey: ['testcase-groups'],
    queryFn: fetchGroups,
    staleTime: 30_000,
  })
}
