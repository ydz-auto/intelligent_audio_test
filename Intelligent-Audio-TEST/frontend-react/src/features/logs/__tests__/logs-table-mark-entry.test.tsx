/**
 * 文件日志行不提供标记入口（INT-1945）。
 * 文件日志游标行（id ≥ 10^12，审计 JSONL）后端只读、不可标记（PUT /logs/mark → updated=0）：
 * 行内「标记」不给入口；历史库行（id < 10^12）照旧可标记。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { LogItem } from '@/domain/models/log'
import { LogsTable } from '@/features/logs/components/logs-table'

function makeLog(overrides: Partial<LogItem>): LogItem {
  return {
    id: 1,
    time: '2026-10-25 10:00:00.000000',
    level: 'INFO',
    category: 'test',
    module: 'task',
    source: 'api_gateway',
    content: '内容',
    mark: null,
    deviceId: null,
    taskId: null,
    apiId: null,
    testCaseId: null,
    threadId: null,
    algorithmType: null,
    ...overrides,
  }
}

const FILE_LOG_ID = 1792958227144761 // 审计文件游标行（≥ 10^12，只读）
const LEGACY_LOG_ID = 6849626 // 历史 logs 表行（可标记）

function renderTable(canManage: boolean) {
  return render(
    <LogsTable
      rows={[
        makeLog({ id: FILE_LOG_ID, content: '文件日志' }),
        makeLog({ id: LEGACY_LOG_ID, content: '历史库日志' }),
      ]}
      loading={false}
      total={2}
      searchKeyword=''
      selectedIds={new Set()}
      onToggleSelect={vi.fn()}
      onToggleSelectAll={vi.fn()}
      canManage={canManage}
      expandedId={null}
      onToggleExpand={vi.fn()}
      onMark={vi.fn()}
      sort={null}
      onToggleSort={vi.fn()}
    />
  )
}

describe('LogsTable 标记入口（INT-1945）', () => {
  it('文件日志行无「标记」，历史库行保留', () => {
    renderTable(true)

    expect(screen.queryByLabelText(`标记日志 ${FILE_LOG_ID}`)).toBeNull()
    expect(screen.getByLabelText(`标记日志 ${LEGACY_LOG_ID}`)).not.toBeNull()
  })

  it('无 log:manage 权限两行都无标记入口（权限门不回归）', () => {
    renderTable(false)

    expect(screen.queryByLabelText(`标记日志 ${FILE_LOG_ID}`)).toBeNull()
    expect(screen.queryByLabelText(`标记日志 ${LEGACY_LOG_ID}`)).toBeNull()
  })
})
