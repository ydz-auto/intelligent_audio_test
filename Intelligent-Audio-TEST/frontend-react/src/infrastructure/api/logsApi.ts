/**
 * 日志维护/归档 API 桩（infrastructure 层，红线④：mock 常量）。
 * 契约对照 api_gateway/schemas/log.py 实测（INT-381 裁定归档 UI 落点设置工作区）：
 * GET /logs/archive/status、GET /logs/archive/logs、POST /logs/archive、
 * DELETE /logs/archive/{filename}；权限口径 log:read=状态/列表/下载、log:manage=归档/删除。
 * TODO(API 接线): fetch 换真实 client；mock 写操作仅本地数组变更。
 */
import type {
  LogArchiveItem,
  LogArchiveStatus,
} from '@/domain/models/log-archive'
import {
  MOCK_ARCHIVE_ITEMS,
  MOCK_ARCHIVE_STATUS,
} from '@/infrastructure/mock/logs-mock'

export const ARCHIVE_STATUS_QUERY_KEY = ['operations', 'archive-status'] as const
export const ARCHIVE_LIST_QUERY_KEY = ['operations', 'archive-list'] as const

export async function getArchiveStatus(): Promise<LogArchiveStatus> {
  return MOCK_ARCHIVE_STATUS
}

export async function getArchiveItems(): Promise<LogArchiveItem[]> {
  return MOCK_ARCHIVE_ITEMS
}

export async function archiveLogsNow(): Promise<LogArchiveItem> {
  const item: LogArchiveItem = {
    filename: `system-${new Date().toISOString().slice(0, 10)}.tar.gz`,
    archivedAt: new Date().toISOString(),
    sizeBytes: 1024 * 1024,
  }
  MOCK_ARCHIVE_ITEMS.unshift(item)
  MOCK_ARCHIVE_STATUS.archiveFiles = MOCK_ARCHIVE_ITEMS.map((i) => i.filename)
  return item
}

export async function deleteMockArchive(filename: string): Promise<void> {
  const index = MOCK_ARCHIVE_ITEMS.findIndex((i) => i.filename === filename)
  if (index !== -1) MOCK_ARCHIVE_ITEMS.splice(index, 1)
  MOCK_ARCHIVE_STATUS.archiveFiles = MOCK_ARCHIVE_ITEMS.map((i) => i.filename)
}
