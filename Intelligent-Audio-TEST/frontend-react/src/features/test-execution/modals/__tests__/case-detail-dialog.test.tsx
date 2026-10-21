/**
 * 用例执行详情模态窗「人工复核 / AI 复核」入口测试（INT-1064/INT-1066，10 规范 §5.2 注记 3）。
 * 分节①区头右侧「人工复核」/「AI 复核」两钮：终态任务 + fetchCaseResults 有执行结果 + 对应权限
 * （task.result.review → 19 §3.2 弹窗；task.result.ai_review → 19 §5 灵犀Agent 复核会话）。
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
// 复核会话/弹窗本体已由浏览器实测 + 关联用例入口验证；本测试聚焦入口接线，用轻量桩
vi.mock('@/features/ai-review/ai-review-session-dialog', () => ({
  AiReviewSessionDialog: ({ open, caseId }: { open: boolean; caseId: string }) =>
    open ? <div data-testid='ai-review-session-dialog' data-case={caseId} /> : null,
}))
vi.mock('@/features/tasks/components/manual-review-dialog', () => ({
  ManualReviewDialog: ({ open, caseName }: { open: boolean; caseName?: string }) =>
    open ? <div data-testid='manual-review-dialog' data-case={caseName} /> : null,
}))

const detail = {
  caseId: 'case-1',
  taskId: 417,
  name: '用例一',
  executionStatus: 'completed',
  evaluationStatus: 'completed',
  duration: 3,
  score: 85,
  algorithmType: 'voice_llm',
  algorithmResults: [],
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
/** API/voice_llm 用例样本（devices 空；INT-1066 返工 P2：分节①展示结果摘要而非「暂无执行结果」） */
const apiDetail = {
  caseId: 'case-2',
  taskId: 1257,
  name: 'API用例',
  executionStatus: 'failed',
  evaluationStatus: 'completed',
  duration: null,
  score: null,
  algorithmType: 'voice_llm',
  algorithmResults: [
    { paramCode: 'session_id', paramType: 'text', label: 'session ID', value: '644fcae7' },
    { paramCode: 'round_count', paramType: 'number', label: 'round count', value: 2 },
    { paramCode: 'total_latency', paramType: 'number', label: 'total latency(ms)', value: 16.544 },
  ],
  devices: [],
}
const apiCaseResults = {
  taskId: 1257,
  caseId: 'case-2',
  caseName: 'API用例',
  results: [{ id: 3693, deviceName: null, apiName: null, executionStatus: 'completed', responseTime: 16544 }],
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

describe('CaseDetailDialog 分节①「人工复核 / AI 复核」入口（INT-1064/INT-1066）', () => {
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

  it('终态任务 + 有执行结果 + 权限 → 分节①区头右侧「人工复核」钮显，点击打开复核弹窗', async () => {
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    const btn = await screen.findByRole('button', { name: '人工复核' })
    expect(btn).toBeInTheDocument()
    await userEvent.click(btn)
    await waitFor(() => {
      expect(screen.getByTestId('manual-review-dialog')).toBeInTheDocument()
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

  it('非终态任务 → 人工复核/AI 复核入口均隐藏', async () => {
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'running' })
    renderDialog()
    await waitFor(() => {
      expect(fetchResultsMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  it('无执行结果 → 人工复核/AI 复核入口均隐藏', async () => {
    fetchTaskMock.mockResolvedValue(taskTerminal)
    fetchResultsMock.mockResolvedValue({ ...caseResults, results: [] })
    renderDialog()
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  it('无 task.result.review 权限 → 人工复核入口隐藏、AI 复核仍显', async () => {
    fetchTaskMock.mockResolvedValue(taskTerminal)
    useAuthStore.setState({
      user: {
        id: '1',
        username: 'algo_engineer',
        displayName: 'algo_engineer',
        roleName: 'algo_engineer',
        permissions: ['task.result.ai_review'],
      },
    })
    renderDialog()
    await waitFor(() => {
      expect(fetchResultsMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    const aiBtn = await screen.findByRole('button', { name: 'AI 复核' })
    expect(aiBtn).toBeInTheDocument()
  })

  // ---- INT-1066 返工 P2：API/voice_llm 用例（devices 空）分节①结果摘要 ----
  it('API 用例（devices 空）有执行结果 → 分节①展示结果摘要而非「暂无执行结果」，复核钮可用', async () => {
    fetchDetailMock.mockResolvedValue(apiDetail)
    fetchResultsMock.mockResolvedValue(apiCaseResults)
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'completed' })
    renderDialog()
    // 结果行摘要渲染（执行完成 + 响应时间 + 算法结果指标），不再出现「暂无执行结果」
    const summary = await screen.findByText('16544ms')
    expect(summary).toBeInTheDocument()
    expect(screen.queryByText('暂无执行结果')).not.toBeInTheDocument()
    expect(screen.getByText('round count')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: '人工复核' })).toBeInTheDocument()
  })

  it('API 用例（devices 空）无任何结果 → 分节①「暂无执行结果」且复核入口隐藏', async () => {
    fetchDetailMock.mockResolvedValue({ ...apiDetail, algorithmResults: [] })
    fetchResultsMock.mockResolvedValue({ ...apiCaseResults, results: [] })
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'completed' })
    renderDialog()
    await waitFor(() => {
      expect(screen.getByText('暂无执行结果')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  it('E2E 用例（devices 非空）时长 null → 头部不渲染「耗时」', async () => {
    fetchDetailMock.mockResolvedValue({ ...detail, duration: null })
    renderDialog()
    await waitFor(() => {
      expect(screen.queryByText(/耗时/)).not.toBeInTheDocument()
    })
  })
})
