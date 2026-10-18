/**
 * 日志 API（infrastructure 层，INT-729 归档接线 + INT-763 /logs 页接线）。
 * 契约对照 api_gateway/routes/log_bp.py + schemas/log.py + log_query/log_command_service：
 * GET /logs（LogListQuery 分页+过滤）、GET /logs/stats、PUT /logs/mark、
 * GET|POST /logs/export、POST /logs/refresh、POST /logs/clear、
 * GET /logs/archive/status（{totalLogs,hotLogs,coldLogs,archiveDir,
 * taskArchives,caseArchives,otherArchives}——归档文件按 任务/用例/其他 前缀计数）；
 * POST /logs/archive（{days?,dry_run?}）、DELETE /logs/archive/{filename}、
 * POST /logs/clear（{before_datetime?,keep_marked?}）；权限 log:read=列表/统计/导出、
 * log:manage=标记/刷新/清除/归档/删除。
 * 注：后端全局归档文件清单接口待 FEAT 卡 INT-780 落地（get_archived_logs 需 task_id/test_case_id）；
 * 落地前归档列表在本层返回空 + 页面「待 INT-780」标记。
 */
import { apiClient } from './client'
import type { LogArchiveItem, LogArchiveStatus } from '@/domain/models/log-archive'
import type {
  Log,
  LogPage,
  LogStatsData,
  LogRefreshResult,
  LogQuery,
  LogExportQuery,
} from '@/domain/models/log'
import { toLogArchiveStatus } from '@/infrastructure/adapters/dto/iam-adapter'
import {
  toLogClearDto,
  toLogMarkDto,
  toLogPage,
  toLogQueryDto,
  toLogRefreshRequestDto,
  toLogRefreshResult,
  toLogStatsData,
} from '@/infrastructure/adapters/logAdapter'
import type {
  LogArchiveResultDto,
  LogArchiveStatusDto,
} from '@/infrastructure/dto/iam.dto'
import type {
  LogListDto,
  LogRefreshDto,
  LogStatsDto,
} from '@/infrastructure/dto/log.dto'

export const ARCHIVE_STATUS_QUERY_KEY = ['operations', 'archive-status'] as const
export const ARCHIVE_LIST_QUERY_KEY = ['operations', 'archive-list'] as const
export const LOG_LIST_QUERY_KEY = ['logs', 'list'] as const
export const LOG_STATS_QUERY_KEY = ['logs', 'stats'] as const

/** GET /logs（LogListQuery 分页 + 过滤；log:read） */
export async function fetchLogs(params: LogQuery = {}): Promise<LogPage> {
  const dto = await apiClient.get<LogListDto>('/logs', { params: toLogQueryDto(params) })
  return toLogPage(dto)
}

/** GET /logs/stats（按级别细分计数；log:read） */
export async function fetchLogStats(params: LogQuery = {}): Promise<LogStatsData> {
  const dto = await apiClient.get<LogStatsDto>('/logs/stats', { params: toLogQueryDto(params) })
  return toLogStatsData(dto)
}

/** PUT /logs/mark（log_ids + mark；log:manage） */
export async function markLogs(
  logIds: (string | number)[],
  mark = 'flagged'
): Promise<void> {
  await apiClient.put('/logs/mark', toLogMarkDto({ logIds, mark }))
}

/** GET/POST /logs/export（log:read）。
 * 后端 export_logs 实测（log_query_service.py:325-373）：LogExportRequest{log_ids,format}
 * 从 POST body 解析、LogExportQuery{level,module} 从 query 解析，响应为 FileResponse
 * 原始文件流（txt/json/csv/xlsx），非 zip_base64。故本层 POST 携带 format/log_ids、
 * query 携带 level/module，下载 Blob 到本地。 */
export async function exportLogs(query: LogExportQuery = {}): Promise<void> {
  const blob = await apiClient.post<Blob>(
    '/logs/export',
    {
      log_ids: query.logIds ? query.logIds.split(',') : undefined,
      format: query.format ?? 'txt',
    },
    {
      params: { level: query.level, module: query.module },
      responseType: 'blob',
    }
  )
  const extMap: Record<string, string> = { txt: 'txt', json: 'json', csv: 'csv', excel: 'xlsx' }
  const ext = extMap[query.format ?? 'txt'] ?? 'txt'
  const date = new Date().toISOString().slice(0, 10)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `logs_export_${date}.${ext}`
  anchor.click()
  URL.revokeObjectURL(url)
}

/** POST /logs/refresh（last_id 增量拉取；log:manage） */
export async function refreshLogs(lastId: string | number = 0): Promise<LogRefreshResult> {
  const dto = await apiClient.post<LogRefreshDto>(
    '/logs/refresh',
    toLogRefreshRequestDto(lastId)
  )
  return toLogRefreshResult(dto)
}

export async function getArchiveStatus(): Promise<LogArchiveStatus> {
  const dto = await apiClient.get<LogArchiveStatusDto>('/logs/archive/status')
  return toLogArchiveStatus(dto)
}

export async function getArchiveItems(): Promise<LogArchiveItem[]> {
  // 后端全局归档文件清单接口待 FEAT 卡 INT-780 落地（get_archived_logs 需 task_id/test_case_id，
  // log_query_service.py:410 实测 400）；落地前返回空列表，页面呈现「待 INT-780」标记。
  return []
}

export async function archiveLogsNow(dryRun = false): Promise<LogArchiveResultDto> {
  return apiClient.post<LogArchiveResultDto>('/logs/archive', {
    dry_run: dryRun,
  })
}

export async function deleteArchive(filename: string): Promise<void> {
  await apiClient.delete(`/logs/archive/${encodeURIComponent(filename)}`)
}

export async function downloadArchive(filename: string): Promise<Blob> {
  return apiClient.get<Blob>(`/logs/archive/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
}

export async function clearLogs(beforeDatetime?: string, keepMarked = true): Promise<void> {
  await apiClient.post('/logs/clear', toLogClearDto({
    beforeDatetime,
    keepMarked,
  }))
}

export type { Log }
