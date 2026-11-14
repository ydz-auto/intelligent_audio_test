/**
 * 报告工作模式·文档面板的空态分支（INT-2473 返工 P2-2）。
 *
 * 任务上下文要先 `GET /reports/by_task/{id}` 解析出报告 id，解析中 / 解析完无报告 /
 * 真正未绑定是三种不同的事实，不能落到同一句「未绑定报告上下文」：
 * - 解析中 → 「正在解析任务关联报告…」（不闪错误提示）；
 * - 解析完 404（fetchReportIdByTask 吞成 null）→ 「该任务暂无关联报告」；
 * - 解析接口失败 → 错误块 + 重试；
 * - 真没绑上下文 → 仍旧「未绑定报告上下文」。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DocumentPanel } from '../document-panel'

/** 文档夹具：useStudioDocuments / useStudioDocument 的 mock 共用（vi.hoisted 可被工厂引用） */
const studioState = vi.hoisted(() => ({ docs: [] as Record<string, unknown>[] }))
const approvalsState = {
  pendingCount: 0,
  isLoading: false,
  isError: false,
}

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true }),
}))

vi.mock('@/application/reports/use-report-studio', () => ({
  useStudioDocuments: () => ({
    data: { items: studioState.docs },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useStudioDocument: (docId: string | null) => ({
    data: studioState.docs.find((doc) => doc.docId === docId) ?? null,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useCreateStudioDocument: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
  useUpdateStudioDocument: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
  // 有文档时面板会挂版本链 / 导出弹窗，这两个子组件的 hook 一并给空实现
  useStudioDocumentVersions: () => ({
    data: [],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useRestoreStudioDocumentVersion: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
  useCreateStudioExportJob: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
  useStudioExportJob: () => ({
    data: null,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}))

vi.mock('@/features/ai-chat/hooks/use-pending-approvals', () => ({
  usePendingApprovals: () => approvalsState,
}))

vi.mock('@/components/ai-elements/response', () => ({
  Response: ({ children }: { children: string }) => <div>{children}</div>,
}))

function renderPanel(
  props: Partial<ComponentProps<typeof DocumentPanel>> = {}
) {
  return render(
    <DocumentPanel
      onClose={() => {}}
      reportId={null}
      sourceId={null}
      sourceKind={null}
      {...props}
    />
  )
}

describe('DocumentPanel 上下文空态', () => {
  beforeEach(() => {
    studioState.docs = []
  })

  it('任务上下文解析中 → 「正在解析任务关联报告…」，不显示「未绑定」', () => {
    renderPanel({ reportId: null, resolvePending: true, sourceKind: 'task', sourceId: '451' })
    expect(screen.getByText('正在解析任务关联报告…')).toBeInTheDocument()
    expect(screen.queryByText('未绑定报告上下文')).not.toBeInTheDocument()
    expect(screen.queryByText('该任务暂无关联报告')).not.toBeInTheDocument()
  })

  it('任务上下文解析完但该任务没有报告 → 「该任务暂无关联报告」，不显示「未绑定」', () => {
    renderPanel({ reportId: null, sourceKind: 'task', sourceId: '451' })
    expect(screen.getByText('该任务暂无关联报告')).toBeInTheDocument()
    expect(screen.queryByText('未绑定报告上下文')).not.toBeInTheDocument()
  })

  it('任务上下文解析接口失败 → 错误块 + 重试，不冒充「该任务暂无报告」', () => {
    const onRetryResolve = vi.fn()
    renderPanel({
      onRetryResolve,
      reportId: null,
      resolveError: '网络错误',
      sourceKind: 'task',
      sourceId: '451',
    })
    expect(screen.getByText(/任务关联报告解析失败/)).toBeInTheDocument()
    expect(screen.getByText(/网络错误/)).toBeInTheDocument()
    expect(screen.queryByText('该任务暂无关联报告')).not.toBeInTheDocument()
    screen.getByRole('button', { name: '重试' }).click()
    expect(onRetryResolve).toHaveBeenCalledTimes(1)
  })

  it('解析失败的文案是空串时也走错误块（空串不得落进「暂无关联报告」）', () => {
    renderPanel({
      reportId: null,
      resolveError: '',
      sourceKind: 'task',
      sourceId: '451',
    })
    expect(screen.getByTestId('studio-task-resolve-error')).toBeInTheDocument()
    expect(screen.getByText('任务关联报告解析失败')).toBeInTheDocument()
    expect(screen.queryByText('该任务暂无关联报告')).not.toBeInTheDocument()
  })

  it('真正没有绑定上下文 → 仍提示先绑定报告上下文', () => {
    renderPanel()
    expect(screen.getByText('未绑定报告上下文')).toBeInTheDocument()
  })

  it('不在 Agent run 中 → 审批条说明当前是手动直写，不冒充「无待审批」', () => {
    renderPanel({ runId: null })
    expect(
      screen.getByText(/未在 Agent run 中/)
    ).toBeInTheDocument()
    expect(screen.queryByText('审批：当前 run 无待审批写操作')).not.toBeInTheDocument()
  })
})

describe('DocumentPanel 多文档切换（P3-1）', () => {
  beforeEach(() => {
    studioState.docs = [
      {
        createdAt: '2026-11-14T06:20:00',
        currentVersion: 1,
        docId: 'd-2',
        markdownContent: '# 第二份',
        sourceFormat: null,
        title: '接线测试 第二份文档',
        updatedAt: '2026-11-14T06:20:00',
      },
      {
        createdAt: '2026-11-14T06:10:00',
        currentVersion: 3,
        docId: 'd-1',
        markdownContent: '# 草稿',
        sourceFormat: null,
        title: '报告草稿',
        updatedAt: '2026-11-14T06:10:00',
      },
    ]
  })

  it('默认最新一份；页签可切到另一份，头部标题与正文跟着换', () => {
    renderPanel({ reportId: 426, sourceId: '426', sourceKind: 'report' })
    expect(screen.getByTestId('studio-doc-title')).toHaveTextContent(
      '接线测试 第二份文档'
    )
    expect(screen.getAllByRole('tab')).toHaveLength(2)

    fireEvent.click(screen.getByRole('tab', { name: /报告草稿/ }))

    expect(screen.getByTestId('studio-doc-title')).toHaveTextContent('报告草稿')
    expect(screen.getByText('# 草稿')).toBeInTheDocument()
  })

  it('只有一份文档时不渲染页签行', () => {
    studioState.docs = [studioState.docs[1]]
    renderPanel({ reportId: 426, sourceId: '426', sourceKind: 'report' })
    expect(screen.queryAllByRole('tab')).toHaveLength(0)
  })
})
