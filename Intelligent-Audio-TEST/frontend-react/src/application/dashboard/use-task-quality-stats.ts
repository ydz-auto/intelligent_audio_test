/**
 * 质量统计 query（application 层）：通过率 / 平均得分卡数据源。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchTaskQualityStats } from '@/infrastructure/api/tasks-api'

export function useTaskQualityStats() {
  return useQuery({
    queryKey: ['tasks', 'quality-stats'],
    queryFn: fetchTaskQualityStats,
    staleTime: 30_000,
  })
}
