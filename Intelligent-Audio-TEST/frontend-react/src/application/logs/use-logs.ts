/**
 * 日志查看页 query hooks（application 层；17_配置运维.md §4）。
 * 列表/统计走 GET /logs、GET /logs/stats（log:read）；标记/导出/清除走
 * PUT /logs/mark、POST /logs/export、POST /logs/clear。queryKey 前缀 ['logs', ...]
 * 与 infrastructure/api/logsApi 共享，实时轮询增量 invalidate 后自动刷新。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  LOG_LIST_QUERY_KEY,
  LOG_STATS_QUERY_KEY,
  clearLogs,
  exportLogs,
  fetchLogStats,
  fetchLogs,
  markLogs,
} from '@/infrastructure/api/logsApi'
import type { LogExportQuery, LogQuery } from '@/domain/models/log'

/** 日志分页列表（查询参数对象 → 结构性 hash key，分页/筛选变化即重新请求） */
export function useLogsQuery(query: LogQuery) {
  return useQuery({
    queryKey: [...LOG_LIST_QUERY_KEY, query],
    queryFn: () => fetchLogs(query),
    staleTime: 5_000,
  })
}

/** 日志统计（GET /logs/stats；加载失败静默隐藏统计行——现状行为，错误交给 query 状态） */
export function useLogStatsQuery(query: LogQuery) {
  return useQuery({
    queryKey: [...LOG_STATS_QUERY_KEY, query],
    queryFn: () => fetchLogStats(query),
    staleTime: 3_000,
  })
}

/** 标记 / 导出 / 清除 mutations（log:manage=标记/清除；log:read=导出） */
export function useLogMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['logs'] })
  }

  const mark = useMutation({
    mutationFn: ({ logIds, mark }: { logIds: (string | number)[]; mark: string }) =>
      markLogs(logIds, mark),
    onSuccess: (_data, variables) => {
      toast.success(`已标记 ${variables.logIds.length} 条日志`)
      invalidate()
    },
    onError: () => toast.error('标记失败，请稍后重试'),
  })

  const exportMutation = useMutation({
    mutationFn: (query: LogExportQuery) => exportLogs(query),
    onSuccess: () => toast.success('日志已导出'),
    onError: () => toast.error('导出失败，请稍后重试'),
  })

  const clearMutation = useMutation({
    mutationFn: (input: { beforeDatetime?: string; keepMarked?: boolean }) =>
      clearLogs(input.beforeDatetime, input.keepMarked),
    onSuccess: () => {
      toast.success('日志已清除')
      invalidate()
    },
    onError: () => toast.error('清除失败，请稍后重试'),
  })

  return {
    mark,
    exportLogs: exportMutation,
    clearLogs: clearMutation,
    invalidate,
  }
}
