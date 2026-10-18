/**
 * 日志归档领域模型（domain 层）。
 * 形态对照 api_gateway/log_query_service.get_archive_status 实测（INT-729）：
 * { totalLogs, hotLogs, coldLogs, archiveDir, taskArchives, caseArchives,
 * otherArchives }——归档文件按 任务/用例/其他 前缀计数，无全局文件清单接口。
 */

export type LogArchiveStatus = {
  totalLogs: number
  hotLogs: number
  coldLogs: number
  archiveDir: string
  /** 任务归档文件数 */
  taskArchives: number
  /** 用例归档文件数 */
  caseArchives: number
  /** 其他归档文件数 */
  otherArchives: number
}

export type LogArchiveItem = {
  filename: string
  archivedAt: string
  /** 文件大小（字节） */
  sizeBytes: number
}

/** 归档状态空态（尚未归档） */
export const EMPTY_ARCHIVE_STATUS: LogArchiveStatus = {
  totalLogs: 0,
  hotLogs: 0,
  coldLogs: 0,
  archiveDir: '',
  taskArchives: 0,
  caseArchives: 0,
  otherArchives: 0,
}

/** 归档总数（已归档文件数；状态卡「已归档/未归档」判定口径） */
export function archiveFileCount(status: LogArchiveStatus): number {
  return (
    (status.taskArchives ?? 0) +
    (status.caseArchives ?? 0) +
    (status.otherArchives ?? 0)
  )
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  )
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}
