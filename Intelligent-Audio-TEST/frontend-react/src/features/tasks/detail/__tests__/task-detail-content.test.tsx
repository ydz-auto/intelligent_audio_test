/**
 * 任务详情「API资源管理」渲染接线测试（INT-1241 移除任务类型概念）：
 * ApiResources 区块按真实 apis 数据无条件渲染——有 apis 即显示、无 apis 即隐藏，
 * 不再由任务类型（isApi / deriveTaskType）推导显隐（旧双口径已随概念移除一并消解）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TaskDetailContent } from '../task-detail-content'

const useTaskDetailMock = vi.hoisted(() => vi.fn())

vi.mock('@/application/tasks/use-task-detail', () => ({
  useTaskDetail: (...args: unknown[]) => useTaskDetailMock(...args),
}))

// 权限桩：全部放行，避免操作按钮逻辑干扰资源区断言
vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true, hasAnyPermission: () => true }),
}))

// 组成区桩（INT-1730）：该 hook 内部 useQuery 需要 QueryClientProvider，而本文件只断言
// ApiResources 接线、与容器组成区无关 → 直接按「非容器」桩掉，不为此在测试里搭 QueryClient
vi.mock('@/application/tasks/use-container-composition', () => ({
  useContainerComposition: () => ({
    isContainer: false,
    isLoading: false,
    trace: null,
    entries: [],
    groups: [],
    summary: {
      total: 0,
      failed: 0,
      unevaluated: 0,
      missing: 0,
      taskCount: 0,
      caseCount: 0,
      deviceCount: 0,
    },
    statusDegraded: false,
  }),
}))

// 子卡桩：本测试聚焦 TaskDetailContent 自身 ApiResources 接线
vi.mock('@/features/tasks/detail/task-info-card', () => ({
  TaskInfoCard: () => <div data-testid='task-info-card' />,
}))
vi.mock('@/features/tasks/detail/progress-card', () => ({
  ProgressCard: () => <div data-testid='progress-card' />,
}))
vi.mock('@/features/tasks/detail/case-association', () => ({
  CaseAssociation: () => <div data-testid='case-association' />,
}))
vi.mock('@/features/tasks/detail/realtime-logs', () => ({
  RealtimeLogs: () => <div data-testid='realtime-logs' />,
}))

/** 最小任务详情（资源区断言只关心 apis，device_types 不应影响渲染） */
function makeDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 419,
    name: '小艺拒识E2E测试任务',
    status: 'completed',
    execution_status: 'completed',
    device_types: [] as string[],
    config: {},
    algorithm_type: null,
    algorithm_params: null,
    apis: [
      { id: 1, name: 'ASR 接口', status: 'online' },
    ],
    devices: [],
    cases: [],
    device_count: null,
    api_count: null,
    ...overrides,
  }
}

function renderDetail(overrides: Record<string, unknown> = {}) {
  useTaskDetailMock.mockReturnValue({
    data: makeDetail(overrides),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })
  // TaskDetailContent 渲染期经 useTaskActions() 取 QueryClient（操作按钮/刷新），
  // 测试侧补 Provider；retry/gcTime 与其它域组件测试同法。
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <TaskDetailContent taskId={419} />
    </QueryClientProvider>
  )
}

describe('TaskDetailContent API 资源区（INT-1241 移除任务类型概念）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('apis 非空即显示 API资源管理（websocket_api-only 任务）', () => {
    renderDetail({ device_types: ['websocket_api'], apis: [{ id: 1, name: 'ASR 接口', status: 'online' }] })
    expect(screen.getByText('API资源管理')).toBeInTheDocument()
    expect(screen.getByText('ASR 接口')).toBeInTheDocument()
  })

  it('apis 非空即显示 API资源管理（physical 任务亦显示，不再按类型显隐）', () => {
    renderDetail({ device_types: ['physical'], apis: [{ id: 2, name: 'TTS 接口', status: 'online' }] })
    expect(screen.getByText('API资源管理')).toBeInTheDocument()
    expect(screen.getByText('TTS 接口')).toBeInTheDocument()
  })

  it('apis 为空则不显示 API资源管理', () => {
    renderDetail({ apis: [] })
    expect(screen.queryByText('API资源管理')).not.toBeInTheDocument()
  })
})
