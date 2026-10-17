/**
 * 最近任务详情 query（application 层）：平台概览「最近任务」卡数据源。
 * 最近任务 id 取 /home/stats/summary recent_tasks[0]（最晚创建），
 * 详情复用任务域 GET /api/v1/tasks/{id} 桩（tasks-list-api），接线时随真实 DTO 替换。
 * summary 未就绪（id 未定）时 disabled，卡片随摘要 loading 态显示骨架。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'

export function useLatestTaskDetail(latestTaskId: number | undefined) {
  return useQuery({
    queryKey: ['tasks', 'detail', latestTaskId ?? 'latest'],
    queryFn: () => fetchTaskDetail(latestTaskId ?? 0),
    enabled: latestTaskId != null,
    staleTime: 30_000,
  })
}
