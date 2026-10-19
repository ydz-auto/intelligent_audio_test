/**
 * 日志维护/归档 API（infrastructure 层；INT-729 归档接线 + INT-826 收口引入 design 侧真实契约）。
 * 契约对照 api_gateway/routes/log_bp.py + schemas/log.py + log_query/log_command_service：
 * GET /logs/archive/status（{totalLogs,hotLogs,coldLogs,archiveDir,taskArchives,
 * caseArchives,otherArchives}——归档文件按 任务/用例/其他 前缀计数）、POST /logs/archive
 * （{days?,dry_run?}）、DELETE /logs/archive/{filename}、GET /logs/archive/{filename}
 * （文件下载 Blob）、POST /logs/clear（{before_datetime?,keep_marked?}）；权限
 * log:read=状态/下载、log:manage=归档/删除/清除。供 05_系统设置「日志维护」分区
 * （INT-548 UI 落点 + INT-729 接线）消费。
 * 注：后端全局归档文件清单接口待 FEAT 卡 INT-780 落地（get_archived_logs 需 task_id/
 * test_case_id，log_query_service.py:410 实测 400）；落地前 getArchiveItems 返回空列表 +
 * 页面「待 INT-780」标记。请求一律经 client.ts（JWT 注入 + 统一信封解包 + 401 refresh）。
 */
import { apiClient } from './client'
import type { LogArchiveItem, LogArchiveStatus } from '@/domain/models/log-archive'
import { toLogArchiveStatus } from '@/infrastructure/adapters/dto/iam-adapter'
import type {
  LogArchiveResultDto,
  LogArchiveStatusDto,
} from '@/infrastructure/dto/iam.dto'
import { toLogClearDto } from '@/infrastructure/dto/log.dto'

export const ARCHIVE_STATUS_QUERY_KEY = ['operations', 'archive-status'] as const
export const ARCHIVE_LIST_QUERY_KEY = ['operations', 'archive-list'] as const

/** GET /logs/archive/status（log:read） */
export async function getArchiveStatus(): Promise<LogArchiveStatus> {
  const dto = await apiClient.get<LogArchiveStatusDto>('/logs/archive/status')
  return toLogArchiveStatus(dto)
}

export async function getArchiveItems(): Promise<LogArchiveItem[]> {
  // 后端全局归档文件清单接口待 FEAT 卡 INT-780 落地（get_archived_logs 需 task_id/test_case_id，
  // log_query_service.py:410 实测 400）；落地前返回空列表，页面呈现「待 INT-780」标记。
  return []
}

/** POST /logs/archive（dry_run 演练模式；log:manage） */
export async function archiveLogsNow(dryRun = false): Promise<LogArchiveResultDto> {
  return apiClient.post<LogArchiveResultDto>('/logs/archive', {
    dry_run: dryRun,
  })
}

/** DELETE /logs/archive/{filename}（log:manage） */
export async function deleteArchive(filename: string): Promise<void> {
  await apiClient.delete(`/logs/archive/${encodeURIComponent(filename)}`)
}

/** GET /logs/archive/{filename}（文件流下载；log:read） */
export async function downloadArchive(filename: string): Promise<Blob> {
  return apiClient.get<Blob>(`/logs/archive/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
}

/** POST /logs/clear（日志维护分区「立即清理」；log:manage） */
export async function clearLogs(beforeDatetime?: string, keepMarked = true): Promise<void> {
  await apiClient.post('/logs/clear', toLogClearDto({ beforeDatetime, keepMarked }))
}
