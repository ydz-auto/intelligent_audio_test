/**
 * 日志维护/归档 mock 数据源（infrastructure 层，红线④：mock 常量）。
 * 形态对照 api_gateway/schemas/log.py 实测：
 * LogArchiveStatus(total_logs/hot_logs/cold_logs/archive_files/archive_dir)、
 * 归档列表 GET /logs/archive/logs（文件名/时间/大小）。
 */
import type {
  LogArchiveItem,
  LogArchiveStatus,
} from '@/domain/models/log-archive'

export const MOCK_ARCHIVE_STATUS: LogArchiveStatus = {
  totalLogs: 18640,
  hotLogs: 1240,
  coldLogs: 17400,
  archiveFiles: ['system-2026-09-01.tar.gz', 'system-2026-10-01.tar.gz'],
  archiveDir: '/data/logs/archive',
}

export const MOCK_ARCHIVE_ITEMS: LogArchiveItem[] = [
  {
    filename: 'system-2026-09-01.tar.gz',
    archivedAt: '2026-09-02T02:00:00Z',
    sizeBytes: 482 * 1024 * 1024,
  },
  {
    filename: 'system-2026-10-01.tar.gz',
    archivedAt: '2026-10-02T02:00:00Z',
    sizeBytes: 516 * 1024 * 1024,
  },
]

export async function fetchMockArchiveStatus(): Promise<LogArchiveStatus> {
  return MOCK_ARCHIVE_STATUS
}

export async function fetchMockArchiveItems(): Promise<LogArchiveItem[]> {
  return MOCK_ARCHIVE_ITEMS
}
