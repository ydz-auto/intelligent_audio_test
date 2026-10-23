/**
 * 关联资源区文案接线测试（INT-1241 移除任务类型概念）：
 * 资源区页签标题统一中性「关联资源」，不再按 device_types/资源计数派生「关联API/关联设备」——
 * 任意 device_types（含 websocket_api-only、空 device_types 兜底）均不再出现按类型定文案。
 * 断言目标是被测组件自身 resourceLabel 的接线；base-ui 原语仅透传，
 * 使 worker 启动不受重依赖图拖累（本机多 agent 并行负载高）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import type { TaskDetailData } from '@/domain/models/task'
import { CaseAssociation } from '../case-association'

// 权限桩：全部放行
vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true, hasAnyPermission: () => true }),
}))

// INT-1626：复核范围/历史 hook 桩（本测试不校验网络，只断言徽章口径）
const reviewRecordScopeMock = vi.hoisted(() => vi.fn())
const scopedReviewHistoryMock = vi.hoisted(() => vi.fn())

vi.mock('@/application/tasks/useReview', () => ({
  useReviewRecordScope: reviewRecordScopeMock,
  useScopedReviewHistory: scopedReviewHistoryMock,
}))

// 复核弹窗/浮条桩：本测试聚焦资源区标签文案，不涉及复核交互
vi.mock('@/features/tasks/components/manual-review-batch-bar', () => ({
  ManualReviewBatchBar: () => null,
}))
vi.mock('@/features/tasks/components/manual-review-dialog', () => ({
  ManualReviewDialog: () => null,
}))
vi.mock('@/features/ai-review/ai-review-session-dialog', () => ({
  AiReviewSessionDialog: () => null,
}))
vi.mock('@/features/ai-review/quick-ai-review-dialog', () => ({
  QuickAiReviewDialog: () => null,
}))
vi.mock('@/features/tasks/components/review-history-drawer', () => ({
  ReviewHistoryDrawer: () => null,
  buildCaseNameMap: (cases: Array<{ case_id: string; name: string }>) =>
    new Map(cases.map((c) => [c.case_id, c.name])),
}))
vi.mock('@/infrastructure/api/reviewApi', () => ({
  fetchCaseResults: vi.fn(),
}))

// 非断言目标的重量级组件桩：本测试只断言资源区文案，不与用例卡/徽章交互
vi.mock('@/features/testcases/components/case-card', () => ({
  CaseCard: () => null,
}))
vi.mock('@/features/dashboard/components/ui/status-badge', () => ({
  StatusBadge: () => null,
}))
vi.mock('@/features/tasks/components/ui/progress', () => ({
  Progress: () => null,
}))
vi.mock('@/features/tasks/components/review-badge', () => ({
  ReviewBadge: () => null,
}))

// base-ui 原语透传桩（text 可查询，role 语义不在断言目标内）：
// Card/Tabs/Select/Collapsible/Badge/Button 仅渲染 children，缩短 worker 启动依赖图
vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CollapsibleContent: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
}))
vi.mock('@/components/ui/button', () => ({
  Button: ({ children }: { children?: ReactNode }) => <button>{children}</button>,
}))

/** 最小任务详情（资源区断言只关心 device_types/device_count/api_count，其余补全类型） */
function makeDetail(overrides: Partial<TaskDetailData> = {}): TaskDetailData {
  return {
    id: 419,
    name: '小艺拒识E2E测试任务',
    description: null,
    status: 'completed',
    execution_status: 'completed',
    evaluation_status: 'completed',
    device_types: [],
    config: {},
    algorithm_type: null,
    algorithm_params: null,
    started_at: null,
    completed_at: null,
    expected_total_time: null,
    expected_complete_time: null,
    used_time: null,
    total_cases: 0,
    case_count: 0,
    device_count: null,
    completed_cases: 0,
    failed_cases: 0,
    tags: [],
    cases: [],
    devices: [],
    apis: [],
    created_at: null,
    updated_at: null,
    api_count: null,
    concurrency: null,
    review_count: 0,
    ...overrides,
  }
}

/** 渲染被测组件（useTaskActions/复核 hook 依赖 QueryClient，测试内提供隔离客户端） */
function renderDetail(detail: TaskDetailData) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <CaseAssociation detail={detail} />
    </QueryClientProvider>
  )
}

describe('CaseAssociation 资源区文案（INT-1241 移除任务类型概念）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 默认非容器：范围=页面任务，历史空
    reviewRecordScopeMock.mockReturnValue({
      scope: { taskIds: [419], resultIds: null },
      isContainer: false,
      isLoading: false,
      isError: false,
    })
    scopedReviewHistoryMock.mockReturnValue({
      data: [],
      scope: { taskIds: [419], resultIds: null },
      reviewedResultCount: 0,
      isLoading: false,
      isError: false,
    })
  })

  it('任意 device_types 均显示中性页签「关联资源」', () => {
    renderDetail(makeDetail({ device_types: ['websocket_api'] }))
    expect(screen.getByText('关联资源')).toBeInTheDocument()
    expect(screen.queryByText('关联API')).not.toBeInTheDocument()
    expect(screen.queryByText('关联设备')).not.toBeInTheDocument()
  })

  it('空 device_types + device_count>0（旧 e2e 任务）同样只显示「关联资源」', () => {
    renderDetail(makeDetail({ device_types: [], device_count: 1, api_count: 0 }))
    expect(screen.getByText('关联资源')).toBeInTheDocument()
    expect(screen.queryByText('关联API')).not.toBeInTheDocument()
    expect(screen.queryByText('关联设备')).not.toBeInTheDocument()
  })

  it('空 device_types + api_count>0（旧 API 任务）同样只显示「关联资源」', () => {
    renderDetail(makeDetail({ device_types: [], device_count: 0, api_count: 2 }))
    expect(screen.getByText('关联资源')).toBeInTheDocument()
    expect(screen.queryByText('关联API')).not.toBeInTheDocument()
    expect(screen.queryByText('关联设备')).not.toBeInTheDocument()
  })

  it('physical 任务同样只显示「关联资源」', () => {
    renderDetail(
      makeDetail({ device_types: ['physical'], device_count: 1, api_count: 0 })
    )
    expect(screen.getByText('关联资源')).toBeInTheDocument()
    expect(screen.queryByText('关联API')).not.toBeInTheDocument()
    expect(screen.queryByText('关联设备')).not.toBeInTheDocument()
  })

  /**
   * INT-1626：挑选合并容器详情 review_count 恒 0（容器不拥有 test_results），
   * 复核计数须按来源任务聚合后的条数展示，否则「已复核 n 条 / 查看复核历史」入口不出现。
   */
  it('容器任务：复核计数取来源任务聚合结果（review_count=0 也显示徽章与历史入口）', () => {
    reviewRecordScopeMock.mockReturnValue({
      scope: { taskIds: [419], resultIds: [5715] },
      isContainer: true,
      isLoading: false,
      isError: false,
    })
    scopedReviewHistoryMock.mockReturnValue({
      data: [],
      scope: { taskIds: [419], resultIds: [5715] },
      reviewedResultCount: 1,
      isLoading: false,
      isError: false,
    })
    renderDetail(makeDetail({ id: 556, review_count: 0 }))
    expect(screen.getByText('已复核 1 条')).toBeInTheDocument()
    expect(screen.getByText('查看复核历史')).toBeInTheDocument()
  })

  it('非容器任务：复核计数沿用后端 review_count', () => {
    renderDetail(makeDetail({ review_count: 3 }))
    expect(screen.getByText('已复核 3 条')).toBeInTheDocument()
  })
})
