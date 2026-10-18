/**
 * 日志维护/归档 API（infrastructure 层，INT-729 接线）。
 * 契约对照 api_gateway/routes/log_bp.py + log_query/log_command_service 实测：
 * GET /logs/archive/status（{totalLogs,hotLogs,coldLogs,archiveDir,
 * taskArchives,caseArchives,otherArchives}——归档文件按 任务/用例/其他 前缀计数）；
 * POST /logs/archive（{days?,dry_run?}）、DELETE /logs/archive/{filename}、
 * POST /logs/clear（{before_datetime?,keep_marked?}）；权限 log:read=状态/列表、
 * log:manage=归档/删除/清理。
 * 注：后端无全局归档文件清单接口（get_archived_logs 需 task_id/test_case_id），
 * 归档列表在本层返回空 + 页面「待接口」标记。
 */
import { apiClient } from './client'
import type { LogArchiveItem, LogArchiveStatus } from '@/domain/models/log-archive'
import { toLogArchiveStatus } from '@/infrastructure/adapters/dto/iam-adapter'
import type {
  LogArchiveResultDto,
  LogArchiveStatusDto,
} from '@/infrastructure/dto/iam.dto'

export const ARCHIVE_STATUS_QUERY_KEY = ['operations', 'archive-status'] as const
export const ARCHIVE_LIST_QUERY_KEY = ['operations', 'archive-list'] as const

export async function getArchiveStatus(): Promise<LogArchiveStatus> {
  const dto = await apiClient.get<LogArchiveStatusDto>('/logs/archive/status')
  return toLogArchiveStatus(dto)
}

export async function getArchiveItems(): Promise<LogArchiveItem[]> {
  // 后端缺全局归档文件清单接口（get_archived_logs 需 task_id/test_case_id，
  // log_query_service.py:410 实测 400）；返回空列表，页面呈现「待接口」标记。
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

export async function clearLogs(beforeDatetime?: string): Promise<void> {
  await apiClient.post('/logs/clear', {
    before_datetime: beforeDatetime,
    keep_marked: true,
  })
}
