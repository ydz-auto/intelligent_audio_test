/**
 * 日志列表/统计 query（application 层；INT-693 接线，17_配置运维.md §4.2/§4.3）。
 * 列表 GET /logs 分页、统计 GET /logs/stats 短 TTL 3s；两者共享同一筛选 query
 * （页面 useMemo 同源装配，验收 3 跨组件同源）→ 改筛选即换 queryKey 同源刷新，
 * 统计徽章与表格/导出摘要随筛选同源联动。
 */
import { useQuery } from '@tanstack/react-query'

import type { LogQuery } from '@/domain/models/log'
import {
  getLogs,
  getLogStats,
  LOG_LIST_QUERY_KEY,
  LOG_STATS_QUERY_KEY,
} from '@/infrastructure/api/logsApi'

/** 日志分页列表（log:read；query 全字段入 key，筛选变更即换 key 重拉） */
export function useLogListQuery(query: LogQuery) {
  return useQuery({
    queryKey: [...LOG_LIST_QUERY_KEY, query],
    queryFn: () => getLogs(query),
    staleTime: 5_000,
  })
}

/**
 * 日志统计（log:read；短 TTL 3s——实时增量时徽章跟随新日志）。
 * enabled=false 用于「不在页面上常驻显示」的估算（如清除弹窗范围估算），
 * 关闭时不发请求、data 为 undefined。
 */
export function useLogStatsQuery(
  query: LogQuery,
  options: { enabled?: boolean } = {}
) {
  return useQuery({
    queryKey: [...LOG_STATS_QUERY_KEY, query],
    queryFn: () => getLogStats(query),
    staleTime: 3_000,
    enabled: options.enabled ?? true,
  })
}
