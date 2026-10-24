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

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchCaseExecutionDetail: fetchDetailMock,
  fetchCaseLogs: fetchLogsMock,
}))
vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchTaskDetail: fetchTaskMock,
}))
// 复核会话/弹窗本体已由浏览器实测 + 关联用例入口验证；本测试聚焦入口接线，用轻量桩
vi.mock('@/features/ai-review/ai-review-session-dialog', () => ({
  AiReviewSessionDialog: ({
    open,
    caseId,
    dimensionIds,
  }: {
    open: boolean
    caseId: string
    dimensionIds?: number[]
  }) =>
    open ? (
      <div
        data-testid='ai-review-session-dialog'
        data-case={caseId}
        data-dims={JSON.stringify(dimensionIds)}
      />
    ) : null,
}))
vi.mock('@/features/tasks/components/manual-review-dialog', () => ({
  ManualReviewDialog: ({ open, caseName }: { open: boolean; caseName?: string }) =>
    open ? <div data-testid='manual-review-dialog' data-case={caseName} /> : null,
}))

const caseResults = [
  {
    id: 5400,
    deviceId: 10,
    deviceName: 'pura90豆包',
    apiId: null,
    apiName: null,
    executionStatus: 'completed',
    responseTime: 0,
    errorMessage: null,
    reviewed: false,
    reviewedByUserId: null,
    reviewedAt: null,
    lastReviewComment: null,
    lastReviewAction: null,
    reviewHistory: [],
    sourceTaskId: 417,
    sourceTaskName: null,
    dimensions: [],
  },
]

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
  metricConfigs: [{ code: '清晰度', name: '清晰度' }],
  metricColumns: [{ key: '清晰度', label: '清晰度', dimension: '清晰度' }],
  multiRound: false,
  results: caseResults,
  resultAudios: [],
  referenceAudios: [],
  devices: [
    {
      resultId: 5400,
      deviceId: 10,
      deviceName: 'pura90豆包',
      executionStatus: 'completed',
      metrics: [{ dimension: '清晰度', value: '0.55' }],
      asrReference: null,
      translationReference: null,
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
  metricConfigs: [],
  metricColumns: [],
  multiRound: false,
  results: [
    {
      id: 3693,
      deviceId: null,
      deviceName: null,
      apiId: null,
      apiName: null,
      executionStatus: 'completed',
      responseTime: 16544,
      errorMessage: null,
      reviewed: false,
      reviewedByUserId: null,
      reviewedAt: null,
      lastReviewComment: null,
      lastReviewAction: null,
      reviewHistory: [],
      sourceTaskId: 1257,
      sourceTaskName: null,
      dimensions: [],
    },
  ],
  resultAudios: [],
  referenceAudios: [],
  devices: [],
}
const taskTerminal = { id: 417, name: '任务', status: 'completed' }

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

  it('INT-1279 P2：任务详情查询加载中（taskQuery 未就绪）→ AI 复核入口隐藏，避免 dimension_ids 静默缺省 400', async () => {
    // 任务详情保持 pending（永不 resolve）→ aiReviewReady=false，复核入口不可见
    fetchTaskMock.mockReturnValue(new Promise<never>(() => {}))
    renderDialog()
    await waitFor(() => {
      expect(fetchDetailMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  it('INT-1279 P2：任务详情就绪后点「AI 复核」，按用例评估维度显式传 dimension_ids 给复核会话', async () => {
    fetchTaskMock.mockResolvedValue({
      ...taskTerminal,
      cases: [
        {
          case_id: 'case-1',
          name: '用例一',
          evaluation_dimensions: [
            { id: 121, name: '识别成功' },
            { id: 124, name: '识别失败' },
          ],
        },
      ],
    })
    renderDialog()
    const btn = await screen.findByRole('button', { name: 'AI 复核' })
    expect(btn).toBeInTheDocument()
    await userEvent.click(btn)
    await waitFor(() => {
      expect(screen.getByTestId('ai-review-session-dialog')).toHaveAttribute(
        'data-dims',
        '[121,124]'
      )
    })
  })

  it('非终态任务 → 人工复核/AI 复核入口均隐藏', async () => {
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'running' })
    renderDialog()
    await waitFor(() => {
      expect(fetchDetailMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  it('无执行结果 → 人工复核/AI 复核入口均隐藏', async () => {
    fetchTaskMock.mockResolvedValue(taskTerminal)
    fetchDetailMock.mockResolvedValue({ ...detail, results: [] })
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
      expect(fetchDetailMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    const aiBtn = await screen.findByRole('button', { name: 'AI 复核' })
    expect(aiBtn).toBeInTheDocument()
  })

  // ---- INT-1066 返工 P2：API/voice_llm 用例（devices 空）分节①结果摘要 ----
  it('API 用例（devices 空）有执行结果 → 分节①展示结果摘要而非「暂无执行结果」，复核钮可用', async () => {
    fetchDetailMock.mockResolvedValue(apiDetail)
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
    fetchDetailMock.mockResolvedValue({ ...apiDetail, algorithmResults: [], results: [] })
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'completed' })
    renderDialog()
    await waitFor(() => {
      expect(screen.getByText('暂无执行结果')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '人工复核' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'AI 复核' })).not.toBeInTheDocument()
  })

  // ---- INT-1688：真实响应形态（设备名 / 维度列 / 结果音频）----
  it('INT-1688：设备名 + @round/@overall 维度列 + 结果音频渲染（有结果用例不再空白/恒失败）', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      multiRound: true,
      metricColumns: [
        { key: '接管率占比@round:1', label: '接管率占比@round:1', dimension: '接管率占比', round: 1 },
        { key: '接管率占比@overall', label: '接管率占比@overall', dimension: '接管率占比' },
      ],
      devices: [
        {
          ...detail.devices[0],
          metrics: [
            { dimension: '接管率占比', round: 1, value: '1' },
            { dimension: '接管率占比', value: '1' },
          ],
        },
      ],
      resultAudios: [
        {
          audioName: 'user_wav (第1轮)',
          deviceName: '9-pura90小艺-1.0.0',
          url: null,
          path: 'case_pcm/402/a.wav',
        },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    expect(await screen.findByText('接管率占比@round:1')).toBeInTheDocument()
    expect(screen.getByText('接管率占比@overall')).toBeInTheDocument()
    expect(screen.getByText('user_wav (第1轮)')).toBeInTheDocument()
    // 设备名在头部徽章与表格设备列各出现一次
    expect(screen.getAllByText('pura90豆包').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: '试听' })).toBeInTheDocument()
  })

  it('E2E 用例（devices 非空）时长 null → 头部不渲染「耗时」', async () => {
    fetchDetailMock.mockResolvedValue({ ...detail, duration: null })
    renderDialog()
    await waitFor(() => {
      expect(screen.queryByText(/耗时/)).not.toBeInTheDocument()
    })
  })
})
