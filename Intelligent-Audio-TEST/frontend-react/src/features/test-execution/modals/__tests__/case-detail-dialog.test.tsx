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

import type { CaseRoundTab } from '@/domain/models/testExecution'
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
  // 单轮（无轮次标记）→ 单个「指标」Tab，行=指标、列=设备
  roundTabs: [
    {
      key: 'all',
      label: '指标',
      round: null,
      kind: 'all',
      rows: [{ dimension: '清晰度', values: { pura90豆包: '0.55' } }],
    },
  ],
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
  roundTabs: [],
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

  // ---- INT-1688（返工）：轮次 Tab + 行=指标/列=设备 + 按轮过滤音频 ----
  it('INT-1688：轮次 Tab（第1轮/整体）+ 指标行 + 设备列，不再显示 @round 内部键', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      roundTabs: [
        {
          key: 'round:1',
          label: '第1轮',
          round: 1,
          kind: 'round',
          rows: [{ dimension: '接管率占比', values: { pura90豆包: '1' } }],
        },
        {
          key: 'overall',
          label: '整体',
          round: null,
          kind: 'overall',
          rows: [{ dimension: '接管率占比', values: { pura90豆包: '1' } }],
        },
      ],
      resultAudios: [
        {
          audioName: 'user_wav (第1轮)',
          deviceName: null,
          round: 1,
          url: null,
          path: 'case_pcm/402/a.wav',
        },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    // 轮次 Tab 栏（多 Tab 才显示）；@round / @overall 内部键不出现在界面上
    expect(await screen.findByRole('tab', { name: '第1轮' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '整体' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.queryByText(/@round:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/@overall/)).not.toBeInTheDocument()
    // 行=指标、列=设备（表头设备名 + 头部徽章）
    expect(screen.getByText('指标')).toBeInTheDocument()
    expect(screen.getAllByText('pura90豆包').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('接管率占比')).toBeInTheDocument()
    expect(screen.getByText('user_wav (第1轮)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '试听' })).toBeInTheDocument()
  })

  it('INT-1688 返工：多轮 7 轮 → Tab 切换按轮出值、音频随 Tab 过滤', async () => {
    const roundTabs: CaseRoundTab[] = [1, 2, 3, 4, 5, 6, 7].map((round) => ({
      key: `round:${round}`,
      label: `第${round}轮`,
      round,
      kind: 'round',
      rows: [{ dimension: '合成成功率', values: { pura90豆包: `0.${round}` } }],
    }))
    roundTabs.push({
      key: 'overall',
      label: '整体',
      round: null,
      kind: 'overall',
      rows: [{ dimension: '合成成功率', values: { pura90豆包: '5' } }],
    })
    fetchDetailMock.mockResolvedValue({
      ...detail,
      roundTabs,
      resultAudios: [
        { audioName: '第1轮音频', deviceName: null, round: 1, url: null, path: 'r0.wav' },
        { audioName: '第7轮音频', deviceName: null, round: 7, url: null, path: 'r6.wav' },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    expect(await screen.findByRole('tab', { name: '第1轮' })).toHaveAttribute(
      'aria-selected',
      'true'
    )
    // 默认第 1 轮：只看到第 1 轮音频
    expect(screen.getByText('第1轮音频')).toBeInTheDocument()
    expect(screen.queryByText('第7轮音频')).not.toBeInTheDocument()
    // 切到第 7 轮：值随轮次变化，音频一并过滤
    await userEvent.click(screen.getByRole('tab', { name: '第7轮' }))
    await waitFor(() => {
      expect(screen.getByText('0.7')).toBeInTheDocument()
    })
    expect(screen.getByText('第7轮音频')).toBeInTheDocument()
    expect(screen.queryByText('第1轮音频')).not.toBeInTheDocument()
  })

  it('E2E 用例（devices 非空）时长 null → 头部不渲染「耗时」', async () => {
    fetchDetailMock.mockResolvedValue({ ...detail, duration: null })
    renderDialog()
    await waitFor(() => {
      expect(screen.queryByText(/耗时/)).not.toBeInTheDocument()
    })
  })
})
