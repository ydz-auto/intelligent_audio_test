/**
 * 任务复核历史抽屉测试（INT-795，19 规范 §3.4）。
 * 覆盖：历史条目渲染（时间/操作人/字段徽章/改判原值→新值/备注）、空态「暂无复核记录」、
 * 按 resultId 过滤（单条复核弹窗「查看复核历史」入口）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReviewHistoryItem } from '@/domain/models/review'

import { ReviewHistoryDrawer } from '../review-history-drawer'

const fetchReviewHistoryMock = vi.hoisted(() => vi.fn())
const fetchContainerSourceTraceMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/reviewApi', () => ({
  submitReview: vi.fn(),
  fetchReviewHistory: fetchReviewHistoryMock,
  fetchReviewCount: vi.fn(),
  fetchCaseResults: vi.fn(),
  requestAiReview: vi.fn(),
  fetchAiReviewHistory: vi.fn(),
  adoptAiReview: vi.fn(),
  rejectAiReview: vi.fn(),
}))

// INT-1626：范围解析（容器溯源）在本测试里固定为非容器，聚合用例单独覆盖
vi.mock('@/infrastructure/api/cherry-pick-api', () => ({
  fetchContainerSourceTrace: fetchContainerSourceTraceMock,
}))

const historyItems: ReviewHistoryItem[] = [
  {
    id: 1,
    resultId: 5400,
    taskId: 417,
    testCaseId: 'case-1',
    fieldName: 'execution_status',
    oldValue: 'failed',
    newValue: 'completed',
    comment: '人工确认通过',
    createdByUserId: 5,
    createdAt: '2026-10-18T09:20:00.000',
  },
  {
    id: 2,
    resultId: 5400,
    taskId: 417,
    testCaseId: 'case-1',
    fieldName: 'evaluation_status',
    oldValue: 'failed',
    newValue: 'completed',
    comment: '评估复核通过',
    createdByUserId: null,
    createdAt: '2026-10-18T09:21:00.000',
  },
]

function renderDrawer(props?: Partial<Parameters<typeof ReviewHistoryDrawer>[0]>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ReviewHistoryDrawer
        open
        onOpenChange={vi.fn()}
        taskId={417}
        taskName='任务A'
        caseNameMap={{ 'case-1': '用例一' }}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('ReviewHistoryDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchContainerSourceTraceMock.mockResolvedValue(null)
  })

  it('历史条目渲染：用例名 + 字段徽章 + 改判原值→新值 + 备注 + 操作人', async () => {
    fetchReviewHistoryMock.mockResolvedValue(historyItems)
    renderDrawer()
    expect(await screen.findByText('复核历史 — 任务A')).toBeInTheDocument()
    expect(await screen.findByText('共 2 条')).toBeInTheDocument()
    // 用例名在每条历史行用例徽章出现 → 复数断言
    expect(screen.getAllByText('用例一').length).toBe(2)
    expect(screen.getByText('执行状态')).toBeInTheDocument()
    expect(screen.getByText('评估状态')).toBeInTheDocument()
    // 改判：原值 failed（两条行均改判自 failed）+ destructive 箭头「→」
    expect(screen.getAllByText('failed').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('→').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('操作人 用户 #5')).toBeInTheDocument()
    expect(screen.getByText('操作人 —')).toBeInTheDocument()
    expect(screen.getByText('人工确认通过')).toBeInTheDocument()
  })

  it('空态：无记录时显示「暂无复核记录」', async () => {
    fetchReviewHistoryMock.mockResolvedValue([])
    renderDrawer()
    expect(await screen.findByText('暂无复核记录')).toBeInTheDocument()
    expect(screen.queryByText('共 0 条')).toBeInTheDocument()
  })

  it('按 resultId 过滤：单条复核弹窗「查看复核历史」入口只显该结果留痕', async () => {
    fetchReviewHistoryMock.mockResolvedValue([
      ...historyItems,
      { ...historyItems[0], id: 3, resultId: 9999, testCaseId: 'case-other' },
    ])
    renderDrawer({ resultId: 5400 })
    await waitFor(() => expect(screen.getByText('共 2 条')).toBeInTheDocument())
    expect(screen.queryByText('case-other')).not.toBeInTheDocument()
  })

  it('INT-1627 长用例名不撑破抽屉：徽章 max-w-full + 名称 truncate + Tooltip 全文', async () => {
    const longName = '测试用例_JS007_多轮拒识-非目标人拒识-上下文拒识-长时间连续对话-带背景噪声-多人交替发言'
    fetchReviewHistoryMock.mockResolvedValue([
      { ...historyItems[0], testCaseId: 'case-long' },
    ])
    renderDrawer({ caseNameMap: { 'case-long': longName } })

    const name = await screen.findByText(longName)
    // 名称在可收缩的 truncate 容器内（省略号），容器徽章宽度受父级限制
    expect(name).toHaveClass('truncate', 'min-w-0')
    const badge = name.parentElement
    expect(badge).toHaveAttribute('data-slot', 'review-history-case-name')
    expect(badge).toHaveClass('max-w-full', 'min-w-0', 'shrink')
    // 全文未被截断丢失（Tooltip 内容同源；悬停展示由浏览器实测覆盖）
    expect(name).toHaveTextContent(longName)
  })

  it('抽屉未打开时不发复核历史请求（enabled 门控，防 taskId=0 无效请求）', () => {
    renderDrawer({ open: false })
    expect(fetchReviewHistoryMock).not.toHaveBeenCalled()
  })

  it('taskId<=0 时即使打开也不发复核历史请求', () => {
    renderDrawer({ taskId: 0 })
    expect(fetchReviewHistoryMock).not.toHaveBeenCalled()
  })

  /**
   * INT-1626：挑选合并容器不拥有 test_results，复核留痕落在源任务下——
   * 抽屉须按溯源来源任务查历史，并只保留容器引用的结果（来源任务里的其他结果不外泄）。
   */
  it('容器任务：按来源任务聚合历史，仅保留容器引用的结果', async () => {
    fetchContainerSourceTraceMock.mockResolvedValue({
      task_id: 556,
      is_cherry_pick: true,
      total: 2,
      groups: [
        {
          source_task_id: 419,
          source_task_name: '源任务A',
          results: [
            {
              result_id: 5715,
              source_task_id: 419,
              source_task_name: '源任务A',
              source_case_id: 'case-1',
              source_device_id: null,
              source_api_id: null,
              missing: false,
            },
          ],
        },
        {
          source_task_id: 420,
          source_task_name: '源任务B',
          results: [
            {
              result_id: 5716,
              source_task_id: 420,
              source_task_name: '源任务B',
              source_case_id: 'case-1',
              source_device_id: null,
              source_api_id: null,
              missing: false,
            },
          ],
        },
      ],
    })
    fetchReviewHistoryMock.mockImplementation((taskId: number) =>
      Promise.resolve(
        taskId === 419
          ? [
              {
                ...historyItems[0],
                id: 11,
                resultId: 5715,
                taskId: 419,
                comment: '容器内留痕',
              },
            ]
          : // 来源任务 420 的历史不属于容器引用结果（result 9999）→ 过滤掉
            [
              {
                ...historyItems[0],
                id: 12,
                resultId: 9999,
                taskId: 420,
                comment: '外部结果留痕',
              },
            ]
      )
    )

    renderDrawer({ taskId: 556, taskName: '容器任务' })

    expect(await screen.findByText('共 1 条')).toBeInTheDocument()
    expect(fetchReviewHistoryMock).toHaveBeenCalledWith(419)
    expect(fetchReviewHistoryMock).toHaveBeenCalledWith(420)
    expect(screen.getByText('容器内留痕')).toBeInTheDocument()
    // 容器未引用的结果留痕不进入抽屉
    expect(screen.queryByText('外部结果留痕')).not.toBeInTheDocument()
  })
})
