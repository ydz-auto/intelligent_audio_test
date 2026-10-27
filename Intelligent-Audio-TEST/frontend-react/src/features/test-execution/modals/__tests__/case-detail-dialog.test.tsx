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
  resultAudioFields: [],
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
  resultAudioFields: [],
  referenceAudios: [],
  devices: [],
}
const taskTerminal = { id: 417, name: '任务', status: 'completed' }

function renderDialog(caseId = 'case-1') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const ui = (id: string) => (
    <QueryClientProvider client={client}>
      <CaseDetailDialog open onOpenChange={vi.fn()} taskId={417} caseId={id} />
    </QueryClientProvider>
  )
  const result = render(ui(caseId))
  return {
    ...result,
    rerenderCase: (id: string) => result.rerender(ui(id)),
  }
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
  it('API 用例（devices 空）有执行结果 → 分节①渲染 V9.7.10 执行结果全块（设备/API执行结果 kv）而非「暂无执行结果」', async () => {
    fetchDetailMock.mockResolvedValue(apiDetail)
    fetchTaskMock.mockResolvedValue({ ...taskTerminal, status: 'completed' })
    renderDialog()
    // 结果行 + 算法结果指标（INT-2088 起走全块：设备/API执行结果 kv 字段 + 结果行状态；
    // session_id 属 META 字段被过滤，round_count/total_latency 展示）
    await waitFor(() => {
      expect(screen.getByText('round count')).toBeInTheDocument()
    })
    expect(screen.getByText('total latency(ms)')).toBeInTheDocument()
    expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('暂无执行结果')).not.toBeInTheDocument()
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

  // ---- INT-1688（返工）：轮次 Tab + 行=指标/列=设备 + 结果音频两种口径 ----
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
      resultAudioFields: [
        {
          paramCode: 'user_wav@round:1',
          label: 'user_wav',
          round: 1,
          overall: false,
          dimensionName: null,
          deviceName: null,
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
    // 行=指标、列=设备（表头设备名 + 头部徽章）；V9.7.10 评分指标表头「指标名称」
    expect(screen.getByText('指标名称')).toBeInTheDocument()
    expect(screen.getAllByText('pura90豆包').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('接管率占比')).toBeInTheDocument()
    // 执行结果音频字段：label 用原始参数名（轮次只在 chip 上出现一次）
    expect(screen.getByText('user_wav')).toBeInTheDocument()
    expect(screen.queryByText(/user_wav \(第1轮\)/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '试听' })).toBeInTheDocument()
  })

  it('INT-1688 返工 P2：执行结果音频字段随轮次 Tab 过滤，「整体」Tab 无维度归属的全显', async () => {
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
      resultAudioFields: [1, 2, 3, 4, 5, 6, 7].map((round) => ({
        paramCode: `user_wav@round:${round}`,
        label: `r${round}_wav`,
        round,
        overall: false,
        dimensionName: null,
        deviceName: null,
        url: null,
        path: `r${round - 1}.wav`,
      })),
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    expect(await screen.findByRole('tab', { name: '第1轮' })).toHaveAttribute(
      'aria-selected',
      'true'
    )
    // 默认第 1 轮：只看到第 1 轮字段
    expect(screen.getByText('r1_wav')).toBeInTheDocument()
    expect(screen.queryByText('r7_wav')).not.toBeInTheDocument()
    // 切到第 7 轮：值随轮次变化，字段一并过滤
    await userEvent.click(screen.getByRole('tab', { name: '第7轮' }))
    await waitFor(() => {
      expect(screen.getByText('0.7')).toBeInTheDocument()
    })
    expect(screen.getByText('r7_wav')).toBeInTheDocument()
    expect(screen.queryByText('r1_wav')).not.toBeInTheDocument()
    // 「整体」Tab：无维度归属的结果字段全部显示
    await userEvent.click(screen.getByRole('tab', { name: '整体' }))
    await waitFor(() => {
      expect(screen.getByText('r1_wav')).toBeInTheDocument()
    })
    expect(screen.getByText('r7_wav')).toBeInTheDocument()
  })

  it('INT-1688 返工 P2：result_audios 按设备分组，任何轮次 Tab 都显示全部', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      roundTabs: [
        {
          key: 'round:1',
          label: '第1轮',
          round: 1,
          kind: 'round',
          rows: [{ dimension: '合成成功率', values: { pura90豆包: '0.1' } }],
        },
        {
          key: 'overall',
          label: '整体',
          round: null,
          kind: 'overall',
          rows: [{ dimension: '合成成功率', values: { pura90豆包: '5' } }],
        },
      ],
      resultAudios: [
        { audioName: '设备A输出.wav', deviceName: '设备A', round: null, url: '/a.wav', path: null },
        { audioName: '设备B输出.wav', deviceName: '设备B', round: null, url: '/b.wav', path: null },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    // 默认第 1 轮：分组标题＝设备名、两条都在（不按轮次过滤）
    expect(await screen.findByText('设备A输出.wav')).toBeInTheDocument()
    expect(screen.getByText('设备A')).toBeInTheDocument()
    expect(screen.getByText('设备B输出.wav')).toBeInTheDocument()
    expect(screen.getByText('设备B')).toBeInTheDocument()
    // 切到「整体」Tab：仍显示全部
    await userEvent.click(screen.getByRole('tab', { name: '整体' }))
    expect(screen.getByText('设备A输出.wav')).toBeInTheDocument()
    expect(screen.getByText('设备B输出.wav')).toBeInTheDocument()
  })

  it('INT-1688 返工 P3：换用例后轮次 Tab 复位到第一个有数据的 Tab', async () => {
    const sevenTabs: CaseRoundTab[] = [1, 2, 3, 4, 5, 6, 7].map((round) => ({
      key: `round:${round}`,
      label: `第${round}轮`,
      round,
      kind: 'round',
      rows: [{ dimension: '合成成功率', values: { pura90豆包: `0.${round}` } }],
    }))
    sevenTabs.push({
      key: 'overall',
      label: '整体',
      round: null,
      kind: 'overall',
      rows: [{ dimension: '合成成功率', values: { pura90豆包: '5' } }],
    })
    const nextCaseTabs: CaseRoundTab[] = [
      {
        key: 'round:1',
        label: '第1轮',
        round: 1,
        kind: 'round',
        rows: [{ dimension: '合成成功率', values: { pura90豆包: '0.1' } }],
      },
      {
        key: 'overall',
        label: '整体',
        round: null,
        kind: 'overall',
        rows: [{ dimension: '合成成功率', values: { pura90豆包: '5' } }],
      },
    ]
    fetchDetailMock.mockImplementation((_taskId: number, cid: string) =>
      Promise.resolve(
        cid === 'case-1'
          ? { ...detail, roundTabs: sevenTabs }
          : { ...detail, caseId: 'case-2', name: '另一个用例', roundTabs: nextCaseTabs }
      )
    )
    fetchTaskMock.mockResolvedValue(taskTerminal)
    const { rerenderCase } = renderDialog('case-1')
    await screen.findByRole('tab', { name: '第7轮' })
    // 先停在「整体」
    await userEvent.click(screen.getByRole('tab', { name: '整体' }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: '整体' })).toHaveAttribute('aria-selected', 'true')
    })
    // 换用例：不再只做越界钳制（旧实现会落到末位「整体」），复位到第一个有数据的「第1轮」
    rerenderCase('case-2')
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: '第1轮' })).toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByRole('tab', { name: '整体' })).toHaveAttribute('aria-selected', 'false')
  })

  it('INT-1861：同一用例关闭重开后轮次 Tab 复位到第一个有数据的 Tab', async () => {
    const sevenTabs: CaseRoundTab[] = [1, 2, 3, 4, 5, 6, 7].map((round) => ({
      key: `round:${round}`,
      label: `第${round}轮`,
      round,
      kind: 'round',
      rows: [{ dimension: '合成成功率', values: { pura90豆包: `0.${round}` } }],
    }))
    sevenTabs.push({
      key: 'overall',
      label: '整体',
      round: null,
      kind: 'overall',
      rows: [{ dimension: '合成成功率', values: { pura90豆包: '5' } }],
    })
    fetchDetailMock.mockResolvedValue({ ...detail, roundTabs: sevenTabs })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    // 弹窗由父层常驻挂载（open 开关），不是每次打开都重挂——同用例重开必须自己复位
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
    const ui = (isOpen: boolean) => (
      <QueryClientProvider client={client}>
        <CaseDetailDialog open={isOpen} onOpenChange={vi.fn()} taskId={417} caseId="case-1" />
      </QueryClientProvider>
    )
    const { rerender } = render(ui(true))
    await screen.findByRole('tab', { name: '第7轮' })
    // 先停在「整体」
    await userEvent.click(screen.getByRole('tab', { name: '整体' }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: '整体' })).toHaveAttribute('aria-selected', 'true')
    })
    // 关闭（caseId 不变）再重开：复位到第一个有数据的「第1轮」
    rerender(ui(false))
    rerender(ui(true))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: '第1轮' })).toHaveAttribute('aria-selected', 'true')
    })
    expect(screen.getByRole('tab', { name: '整体' })).toHaveAttribute('aria-selected', 'false')
  })

  it('E2E 用例（devices 非空）时长 null → 头部不渲染「耗时」', async () => {
    fetchDetailMock.mockResolvedValue({ ...detail, duration: null })
    renderDialog()
    await waitFor(() => {
      expect(screen.queryByText(/耗时/)).not.toBeInTheDocument()
    })
  })

  // ---- INT-2088：任务用例执行详情模态窗补齐 V9.7.10 全块 ----
  it('INT-2088：评分指标 / 参考数据 / 用例参数空态 / 执行结果块渲染', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      referenceParams: {
        'answer@round:1': { code: 'answer@round:1', type: 'text', text: '第1轮参考答案', round_number: 1 },
        'question@round:1': { code: 'question@round:1', type: 'text', text: '第1轮提问', round_number: 1 },
      },
      fieldMapping: { result: ['session_id'], reference: ['answer@round:1'] },
      algorithmResults: [
        { paramCode: 'session_id', paramType: 'text', label: 'session ID', value: 'abc123' },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    // 块标题：评分指标 + 执行结果
    expect(await screen.findByText('评分指标')).toBeInTheDocument()
    expect(screen.getByText('执行结果')).toBeInTheDocument()
    // 参考数据：referenceParams text kv 按轮展示（label 带轮次，值 = text）
    expect(screen.getByText('参考数据')).toBeInTheDocument()
    expect(screen.getByText('answer (第1轮)')).toBeInTheDocument()
    expect(screen.getByText('第1轮参考答案')).toBeInTheDocument()
    expect(screen.getByText('question (第1轮)')).toBeInTheDocument()
    // 用例参数：后端无 case_params 数据源 → 块内「暂无数据」空态
    expect(screen.getByText('用例参数')).toBeInTheDocument()
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('INT-2088：评估结果（维度 tab）+ 设备/API 执行结果（无维度字段 + 状态行）', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      algorithmResults: [
        { paramCode: 'wer', paramType: 'number', label: 'WER', dimensionName: '清晰度', value: 0.5 },
        { paramCode: 'llm_score', paramType: 'number', label: 'LLM 评分', dimensionName: '清晰度', value: 4 },
        { paramCode: 'device_result', paramType: 'text', label: '设备结果', value: 'ok' },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    expect(await screen.findByText('评估结果')).toBeInTheDocument()
    // 维度 tab 切换（主维度「清晰度」）+ 该维度 kv
    expect(screen.getByRole('tab', { name: '清晰度' })).toBeInTheDocument()
    expect(screen.getByText('WER')).toBeInTheDocument()
    expect(screen.getByText('LLM 评分')).toBeInTheDocument()
    // 设备/API 执行结果：无维度归属字段 + 结果行状态
    expect(screen.getByText('设备/API 执行结果')).toBeInTheDocument()
    expect(screen.getByText('设备结果')).toBeInTheDocument()
    // 执行状态（评分指标表设备徽章 + 结果行状态行均渲染「已完成」）
    expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1)
  })

  it('INT-2088：多轮对话结果（algorithmResults.rounds 检测）聚合卡 + 每轮展开', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      algorithmResults: [
        {
          paramCode: 'multi_round',
          paramType: 'json',
          label: '多轮结果',
          value: {
            rounds: [
              { evaluation: { wer: 0.2, llm_judge: 4, latency: 100 } },
              { evaluation: { wer: 0.3, llm_judge: 3, latency: 200 } },
            ],
            aggregated: { avg_wer: 0.25, avg_llm_judge: 3.5, avg_latency: 150, interruption_count: 0 },
          },
        },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    expect(await screen.findByText('多轮对话结果 (2 轮)')).toBeInTheDocument()
    expect(screen.getByText('平均 WER')).toBeInTheDocument()
    expect(screen.getByText('平均 LLM 评分')).toBeInTheDocument()
    expect(screen.getByText('第 1 轮')).toBeInTheDocument()
  })

  it('INT-2088：多轮对话结果——rounds 值为数组形态（真实库 param_code=rounds json 项）+ latency null 不崩溃', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      algorithmResults: [
        {
          paramCode: 'rounds',
          paramType: 'json',
          label: 'round results',
          value: [
            { round: 0, input: { audio_name: 'r0.wav' }, output: {}, latency: null, evaluation: {}, is_interruption: true },
            { round: 1, input: { audio_name: 'r1.wav' }, output: {}, latency: null, evaluation: {}, is_interruption: false },
          ],
        },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    // value 数组形态 → 检测通过，渲染聚合卡与每轮头；latency null 只渲染「第 N 轮」不崩溃
    expect(await screen.findByText('多轮对话结果 (2 轮)')).toBeInTheDocument()
    expect(screen.getByText('第 1 轮')).toBeInTheDocument()
    expect(screen.getByText('第 2 轮')).toBeInTheDocument()
    expect(screen.queryByText(/延迟 null/)).not.toBeInTheDocument()
  })

  it('INT-2088：时间轴对比（stm 结果字段）+ 音频时间轴（用例输入音频）', async () => {
    fetchDetailMock.mockResolvedValue({
      ...detail,
      algorithmResults: [
        {
          paramCode: 'stm',
          paramType: 'stm',
          label: 'stm',
          value: '说话人1 X 0 2 你好内容\n说话人1 X 2 1 再见内容',
          device: 'pura90豆包',
        },
      ],
      referenceAudios: [
        { audioName: 'JG0006_输入.wav', deviceName: null, audioId: 1622, round: null, url: null, path: null },
      ],
    })
    fetchTaskMock.mockResolvedValue(taskTerminal)
    renderDialog()
    // 时间轴对比：stm 结果字段触发 + 段文本渲染
    expect(await screen.findByText('时间轴对比')).toBeInTheDocument()
    expect(screen.getByText('你好内容')).toBeInTheDocument()
    // 音频时间轴：用例输入音频（audio_list；名字在段 title 上）
    expect(screen.getByText('音频时间轴')).toBeInTheDocument()
    expect(screen.getByTitle(/JG0006_输入\.wav/)).toBeInTheDocument()
  })
})
