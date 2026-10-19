/**
 * 任务详情/日志 query（application 层，09_任务域.md §4）。
 * 详情与快览弹窗共用同一数据源（TaskDetailContent 双形态复用）。
 * 日志分页：page+1=更老；任务运行中 10s 轮询增量 append（mock 态仅首次加载）。
 */
import { useQuery } from '@tanstack/react-query'

import {
  fetchTaskDetail,
  fetchTaskLogs,
} from '@/infrastructure/api/tasks-list-api'

export function useTaskDetail(taskId: number, enabled = true) {
  return useQuery({
    queryKey: ['tasks', 'detail', taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled,
    staleTime: 30_000,
    // INT-932 P2-2：无效任务 id（400 code:203 未找到任务）快速落到错误态，
    // 不重试（默认 retry:1 指数退避会持续请求），错误态由 TaskDetailContent 渲染
    retry: 0,
  })
}

export function useTaskLogs(taskId: number, enabled = true) {
  return useQuery({
    queryKey: ['tasks', 'logs', taskId],
    queryFn: () => fetchTaskLogs(taskId, 1, 20),
    enabled,
    staleTime: 10_000,
    refetchInterval: (query) => {
      // 任务运行中每 10s 轮询增量 append（§4.6 现口径保留；mock 态数据无增量，返回 false）
      return query.state.data ? false : false
    },
  })
}
