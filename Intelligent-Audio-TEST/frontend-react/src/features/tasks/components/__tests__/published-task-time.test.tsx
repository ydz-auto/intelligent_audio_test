/**
 * INT-2664 回归：已发布任务列表「发布人/发布时间」与版本历史「发布时间」
 * 按 +08 墙钟串原样展示。
 *
 * 后端 `published_tasks.published_at` 由 `utc8now` 落库，下发的无时区后缀串
 * （如 `2026-11-20T10:20:46`）本身已是东八区时间；误用 formatDateTime 会按
 * 裸 UTC 解析再转本地，页面显示成 18:20（重复 +8）。
 * 同屏的「执行记录」（test_tasks.created_at，裸 UTC）继续走 formatDateTime，不受影响。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PublishedTaskDetail, PublishedTaskItem } from '@/domain/models/task'
import { formatDateTime } from '@/lib/date-time'

import { PublishedTaskTable } from '../published-task-table'

const fetchPublishedTaskDetailMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchPublishedTaskDetail: fetchPublishedTaskDetailMock,
}))

vi.mock('@/infrastructure/api/tasks-published-actions-api', () => ({
  archivePublishedTask: vi.fn(),
  createPublishedTaskVersion: vi.fn(),
  executePublishedTask: vi.fn(),
  renamePublishedTask: vi.fn(),
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true }),
}))

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))

function buildItem(
  patch: Partial<PublishedTaskItem> = {}
): PublishedTaskItem {
  return {
    id: 3,
    sourceTaskId: 419,
    name: 'INT2662_QA_正式任务_1120',
    description: null,
    type: 'e2e',
    algorithmType: null,
    status: 'published',
    benchmark: false,
    version: 1,
    isCurrent: true,
    versionCount: 2,
    publishedBy: 'dev_user',
    publishedAt: '2026-11-20T10:20:46',
    archivedAt: null,
    createdAt: '2026-11-20T10:20:46',
    ...patch,
  }
}

function renderTable(tasks: PublishedTaskItem[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <PublishedTaskTable tasks={tasks} loading={false} />
    </QueryClientProvider>
  )
}

describe('已发布任务发布时间（INT-2664）', () => {
  it('列表行按 +08 墙钟原样展示，不再二次 +8', () => {
    renderTable([buildItem()])
    expect(screen.getByText('2026-11-20 10:20')).toBeInTheDocument()
    expect(screen.queryByText('2026-11-20 18:20')).not.toBeInTheDocument()
  })

  it('版本历史按 +08 墙钟原样展示；执行记录仍按裸 UTC 换算', async () => {
    const user = userEvent.setup()
    const detail: PublishedTaskDetail = {
      id: 3,
      taskGroupId: 3,
      sourceTaskId: 419,
      name: 'INT2662_QA_正式任务_1120',
      description: null,
      status: 'published',
      benchmark: false,
      version: 2,
      isCurrent: true,
      snapshotConfig: {},
      hasTaskSnapshot: false,
      publishReason: null,
      publishedBy: 'dev_user',
      publishedAt: '2026-11-20T10:20:46',
      archivedBy: null,
      archivedAt: null,
      sourceTaskName: '源任务',
      sourceTaskStatus: 'completed',
      sourceTaskTotalCases: 12,
      sourceTaskCompletedCases: 12,
      reportSnapshot: null,
      hasReportSnapshot: false,
      versions: [
        buildItem({ id: 3, version: 2, publishedAt: '2026-11-20T10:20:46' }),
        buildItem({ id: 2, version: 1, publishedAt: '2026-11-20T09:01:51', isCurrent: false }),
      ],
      executionHistory: [
        {
          taskId: 9,
          taskName: '执行任务',
          version: 2,
          status: 'completed',
          totalCases: 12,
          completedCases: 12,
          createdAt: '2026-11-20T00:05:00',
          completedAt: null,
        },
      ],
    }
    fetchPublishedTaskDetailMock.mockResolvedValue(detail)

    renderTable([buildItem()])
    await user.click(screen.getByRole('button', { name: '展开版本详情' }))

    // 版本历史：v2 与列表行同一发布时刻，v1 另一个墙钟串，均原样展示
    expect(await screen.findByText('2026-11-20 09:01')).toBeInTheDocument()
    expect(screen.getAllByText('2026-11-20 10:20')).toHaveLength(2)
    expect(screen.queryByText('2026-11-20 18:20')).not.toBeInTheDocument()
    expect(screen.queryByText('2026-11-20 17:01')).not.toBeInTheDocument()

    // 执行记录（裸 UTC）口径不变：与 formatDateTime 结果一致
    expect(
      screen.getByText(formatDateTime('2026-11-20T00:05:00'))
    ).toBeInTheDocument()
  })
})
