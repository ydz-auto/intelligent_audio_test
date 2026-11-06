/**
 * 已完成任务列表（application 层，INT-434 P2-20 收敛）。
 * 生成报告 / 对比 Dialog 的任务选择器数据源；页面不直 import mock 常量。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchCompletedTasks } from '@/infrastructure/api/reports-api'

export function useCompletedTasks() {
  return useQuery({
    queryKey: ['reports', 'completed-tasks'],
    queryFn: fetchCompletedTasks,
    staleTime: 60_000,
  })
}
