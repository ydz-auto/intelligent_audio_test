/**
 * 用例执行详情模态窗「AI 复核」入口测试（INT-1064，10 规范 §5.2 注记 3）。
 * 分节①区头右侧「AI 复核」钮：终态任务 + fetchCaseResults 有执行结果 + task.result.ai_review
 * 权限 → 打开灵犀Agent 复核会话（复用 features/ai-review/ai-review-session-dialog）。
 * 无执行结果/非终态/无权限 → 入口隐藏。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/infrastructure/stores/auth-store'

import { CaseDetailDialog } from '../case-detail-dialog'

const fetchDetailMock = vi.hoisted(() => vi.fn())
const fetchLogsMock = vi.hoisted(() => vi.fn())
const fetchTaskMock = vi.hoisted(() => vi.fn())
const fetchResultsMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchCaseExecutionDetail: fetchDetailMock,
  fetchCaseLogs: fetchLogsMock,
}))
vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchTaskDetail: fetchTaskMock,
}))
vi.mock('@/infrastructure/api/reviewApi', () => ({
  fetchCaseResults: fetchResultsMock,
}))
// 复核会话本体已由浏览器实测 + 关联用例入口验证；本测试聚焦入口接线，用轻量桩
vi.mock('@/features/ai-review/ai-review-session-dialog', () => ({
  AiReviewSessionDialog: ({ open, caseId }: { open: boolean; caseId: string }) =>
    open ? <div data-testid='ai-review-session-dialog' data-case={caseId} /> : null,
}))

const detail = {
  caseId: 'case-1',
  taskId: 417,
  name: '用例一',
  executionStatus: 'completed',
  evaluationStatus: 'completed',
  duration: 3,
  score: 85,
  devices: [
    {
      deviceId: 10,
      deviceName: 'pura90豆包',
      status: 'pass' as const,
      duration: 3,
      score: 85,
      metrics: [{ dimension: '清晰度', value: '0.55' }],
      asrReference: null,
      translationReference: null,
      audioResults: [],
    },
  ],
}
const taskTerminal = { id: 417, name: '任务', status: 'completed' }
const caseResults = {
  taskId: 417,
  caseId: 'case-1',
  caseName: '用例一',
  results: [{ id: 5400, deviceName: 'pura90豆包' }],
}

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <CaseDetailDialog open onOpenChange={vi.fn()} taskId={417} caseId='case-1' />
    </QueryClientProvider>
  )
}

describe('CaseDetailDialog 分节①「AI 复核」入口（INT-1064）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchDetailMock.mockResolvedValue(detail)
    fetchLogsMock.mockResolvedValue({ items: [], total: 0, page: 1 })
    fetchResultsMock.mockResolvedValue(caseResults)
    useAuthStore.setState({
      user: {
        id: '1',
        username: 'tester',
        displayName: 'tester',
        roleName: 'tester',
        permissions: ['*'],
      },
    })
  })

  it('终态任务 + 有执行结果 + 权限 → 分节①区头右侧「AI 复核」钮显，点击打开复核会话', async () => {
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    const btn = await screen.findByRole('button', { name: 'AI 复核' })
    expect(btn).toBeInTheDocument()
    await userEvent.click(btn)
    await waitFor(() => {
      expect(screen.getByTestId('ai-review-session-dialog')).toBeInTheDocument()
    })
  })

  it('非终态任务 → 入口隐藏', async () => {
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'running' })
    renderDialog()
    await waitFor(() => {
      expect(fetchResultsMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  it('无执行结果 → 入口隐藏', async () => {
    fetchTaskMock.mockResolvedValue(taskTerminal)
    fetchResultsMock.mockResolvedValue({ ...caseResults, results: [] })
    renderDialog()
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
    })
  })
})
