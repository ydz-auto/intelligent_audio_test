/**
 * 任务详情路由页「关联用例 → 用例执行详情模态窗」接线测试（INT-1066，10 规范 §5.2）。
 * 关联用例行 onCaseSelect（09 §4.4）→ 打开 CaseDetailDialog（任务详情/测试执行共用组件）。
 * TaskDetailContent 已由关联用例卡消费 onCaseSelect（case-association 自测 + 浏览器实测），
 * 本测试以桩触发 onCaseSelect，聚焦路由页接线：点击用例行 → CaseDetailDialog 打开并传入 caseId。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TaskDetailRoutePage } from '../task-detail-route-page'

const useTaskDetailMock = vi.hoisted(() => vi.fn())

vi.mock('@/application/tasks/use-task-detail', () => ({
  useTaskDetail: (...args: unknown[]) => useTaskDetailMock(...args),
}))

// 桩 TaskDetailContent：透出 onCaseSelect 供接线验证（真实组件已由 case-association 覆盖）
vi.mock('@/features/tasks/detail/task-detail-content', () => ({
  TaskDetailContent: ({
    onCaseSelect,
  }: {
    onCaseSelect?: (caseId: string) => void
  }) => (
    <button
      type='button'
      onClick={() => onCaseSelect?.('case-1')}
      data-testid='case-row'
    >
      关联用例行
    </button>
  ),
}))

// 桩 CaseDetailDialog：透出 open/caseId 供接线验证（弹窗本体已由 case-detail-dialog 自测覆盖）
vi.mock('@/features/test-execution/modals/case-detail-dialog', () => ({
  CaseDetailDialog: ({
    open,
    caseId,
  }: {
    open: boolean
    caseId: string
  }) => (open ? <div data-testid='case-detail-dialog' data-case={caseId} /> : null),
}))

// 路由页面包屑/返回钮的 Link（仅渲染桩，不依赖路由树）
vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    className,
    params,
    to,
  }: {
    children?: React.ReactNode
    className?: string
    params?: Record<string, string>
    to?: string
  }) => (
    <a className={className} href={`${to}/${params?.tab ?? ''}`}>
      {children}
    </a>
  ),
}))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <TaskDetailRoutePage taskId={417} />
    </QueryClientProvider>
  )
}

describe('TaskDetailRoutePage 关联用例 → 用例执行详情模态窗（INT-1066）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useTaskDetailMock.mockReturnValue({
      data: { name: '任务A' },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
  })

  it('点击关联用例行 → 打开用例执行详情模态窗并传入 caseId', async () => {
    renderPage()
    const row = screen.getByTestId('case-row')
    await userEvent.click(row)
    const dialog = screen.getByTestId('case-detail-dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('data-case', 'case-1')
  })
})
