/**
 * 日志查看 API（infrastructure 层；INT-693 接线：mock → 真实接口，经 client.ts）。
 * 对照 api_gateway/routes/log_bp.py + schemas/log.py 实测（全部挂 /api/v1 前缀）：
 * GET /logs（log:read，分页列表）、GET /logs/stats（log:read）、
 * PUT /logs/mark（log:manage，{log_ids, mark}）、POST /logs/clear（log:manage，
 * {before_datetime, keep_marked}）、POST /logs/refresh（log:manage，{last_id} 增量）、
 * POST /logs/export（log:read，{log_ids?, format} → 文件流 Blob 下载）。
 * 请求一律经 client.ts（JWT 注入 + 统一信封解包 + 401 refresh）；snake_case↔camelCase
 * 唯一转换收敛在 infrastructure/dto/log.dto.ts，本层只见 Domain。
 */
import type {
  LogClearInput,
  LogExportInput,
  LogItem,
  LogMarkInput,
  LogPage,
  LogQuery,
  LogRefreshResult,
  LogStats,
} from '@/domain/models/log'
import { apiClient } from '@/infrastructure/api/client'
import {
  toLogClearDto,
  toLogExportRequestDto,
  toLogMarkDto,
  toLogPage,
  toLogQueryDto,
  toLogRefreshRequestDto,
  toLogRefreshResult,
  toLogStats,
  type LogListDto,
  type LogRefreshDto,
  type LogStatsDto,
} from '@/infrastructure/dto/log.dto'

export const LOG_LIST_QUERY_KEY = ['logs', 'list'] as const
export const LOG_STATS_QUERY_KEY = ['logs', 'stats'] as const

/** 日志分页列表（log:read；查询参数逐字段映射 toLogQueryDto） */
export async function getLogs(query: LogQuery = {}): Promise<LogPage> {
  const data = await apiClient.get<LogListDto>('/logs', {
    params: toLogQueryDto(query),
  })
  return toLogPage(data)
}

/** 日志统计（log:read；与列表共享短 TTL 扫描缓存语义，见 useLogStats） */
export async function getLogStats(query: LogQuery = {}): Promise<LogStats> {
  const data = await apiClient.get<LogStatsDto>('/logs/stats', {
    params: toLogQueryDto(query),
  })
  return toLogStats(data)
}

/** 标记日志（log:manage；PUT /logs/mark，mark 默认 'flagged'） */
export async function markLogs(input: LogMarkInput): Promise<void> {
  await apiClient.put('/logs/mark', toLogMarkDto(input))
}

/** 清除日志（log:manage；POST /logs/clear → {deletedCount}） */
export async function clearLogs(
  input: LogClearInput
): Promise<{ deletedCount: number }> {
  const data = await apiClient.post<{ deletedCount?: number }>(
    '/logs/clear',
    toLogClearDto(input)
  )
  return { deletedCount: data?.deletedCount ?? 0 }
}

/** 刷新日志（log:manage；POST /logs/refresh，last_id 增量拉取） */
export async function refreshLogs(lastId: string | number = 0): Promise<LogRefreshResult> {
  const data = await apiClient.post<LogRefreshDto>(
    '/logs/refresh',
    toLogRefreshRequestDto(lastId)
  )
  return toLogRefreshResult(data)
}

/**
 * 导出日志（log:read；POST /logs/export，{log_ids?, format} → 文件流 Blob）。
 * 后端为 FileResponse（Excel/CSV/JSON/TXT），前端 responseType: 'blob' 下载。
 * 后端 LogExportQuery 仅支持 level/module 过滤（schemas/log.py 实测），其余筛选
 * 条件（时间范围/分类/关键词等）随 query 透传由后端忽略——导出筛选缺口待后端扩展
 * （见 INT-693 交付评论 §后端缺口）。
 */
export async function exportLogs(
  input: LogExportInput,
  query: LogQuery = {}
): Promise<{ blob: Blob; format: string }> {
  const format = input.format ?? 'txt'
  const blob = await apiClient.post<Blob>('/logs/export', toLogExportRequestDto(input), {
    params: toLogQueryDto(query),
    responseType: 'blob',
  })
  return { blob, format }
}

/** 批量标记（§4.5 浮条；同 PUT /logs/mark，log_ids 为所选行） */
export async function batchMarkLogs(
  logIds: Array<string | number>,
  mark: string
): Promise<void> {
  await markLogs({ logIds, mark })
}

export type { LogItem }
