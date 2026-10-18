/**
 * 日志维护/归档 API（infrastructure 层）。
 * INT-693 拆分：日志查看页（/logs）的 list/stats/mark/clear/export/refresh 真实接口
 * 归 logsApi.ts；本模块保留归档族（GET /logs/archive/status、GET /logs/archive/logs、
 * POST /logs/archive、DELETE /logs/archive/{filename}），供 05_系统设置「日志维护」
 * 分区（INT-548 已落地 UI，INT-381 裁定 UI 落点）消费。
 * TODO(API 接线·归档族): 现状仍为 mock 常量（契约对照 api_gateway/schemas/log.py
 * LogArchiveStatus/LogArchiveResult）；真实后端 /logs/archive/status 返回 raw dict
 * 且无 archive_files 字段、/logs/archive/logs 需 task_id/test_case_id 参数——与设置页
 * 归档小节展示契约不一致，接线缺口另开卡，本模块暂不切换。
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
