/**
 * 日志归档领域模型（domain 层）。
 * 形态对照 api_gateway/schemas/log.py 实测：
 * LogArchiveStatus(total_logs/hot_logs/cold_logs/archive_files/archive_dir)、
 * LogArchiveResult(archived_count/deleted_count/archive_file/remaining_count)。
 */

export type LogArchiveStatus = {
  totalLogs: number
  hotLogs: number
  coldLogs: number
  archiveFiles: string[]
  archiveDir: string
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
  archiveFiles: [],
  archiveDir: '',
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
