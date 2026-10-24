/**
 * 页签行展开（落点③）组件测试（18_挑选合并功能交互重设计.md §5.5.3 ③ / §5.5.6，INT-1716）。
 * 覆盖：收起时不取数（列表首屏零请求）、展开渲染计数行 + 组成四视图、
 * 详情补拉失败 → Empty + 重试、收起再展开不重新挂载（命中缓存）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CherryPickContainer } from '@/domain/models/cherryPick'
import { ContainerTraceExpand } from '@/features/tasks/cherry-pick/components/container-trace-expand'

const useContainerCompositionMock = vi.fn()

vi.mock('@/application/tasks/use-container-composition', () => ({
  useContainerComposition: (taskId: number) => useContainerCompositionMock(taskId),
}))

// 组成区本体由 INT-1711 的单测覆盖，这里只关心挂载时机与空态
vi.mock('@/features/tasks/detail/container-composition', () => ({
  ContainerComposition: () => <div data-testid='composition-stub' />,
}))

const CONTAINER: CherryPickContainer = {
  id: 595,
  name: '接线测试_终审容器',
  description: null,
  executionStatus: 'failed',
  evaluationStatus: 'completed',
  totalCases: 5,
  caseCount: 5,
  failedCases: 2,
  mergeType: 'picked',
  sourceTaskCount: 3,
  sourceResultCount: 5,
  sourceTaskIds: [391, 401, 419],
  sourceTasks: [],
  createdAt: '2026-10-24 03:41',
  isFavorite: false,
}

function model(overrides: Record<string, unknown> = {}) {
  return {
    isContainer: true,
    isLoading: false,
    trace: { taskId: 595, isCherryPick: true, total: 5, groups: [] },
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
    detailLoading: false,
    detailError: false,
    retry: vi.fn(),
    ...overrides,
  }
}

function setupComponent() {
  render(<ContainerTraceExpand container={CONTAINER} />)
  return screen.getByRole('button', { name: /展开组成视图/ })
}

describe('ContainerTraceExpand（§5.5.3 ③ 页签行展开）', () => {
  beforeEach(() => {
    useContainerCompositionMock.mockReset()
    useContainerCompositionMock.mockReturnValue(model())
  })

  it('收起态不取数（列表首屏零新增请求）', () => {
    setupComponent()
    expect(useContainerCompositionMock).not.toHaveBeenCalled()
    expect(screen.queryByTestId('composition-stub')).not.toBeInTheDocument()
  })

  it('展开：按容器 id 取数，保留「来源 n 个任务 · 结果 m 条」计数行并渲染组成区', () => {
    const button = setupComponent()
    fireEvent.click(button)

    expect(useContainerCompositionMock).toHaveBeenCalledTimes(1)
    expect(useContainerCompositionMock).toHaveBeenCalledWith(595)
    expect(screen.getByText('来源 3 个任务 · 结果 5 条')).toBeInTheDocument()
    expect(screen.getByTestId('composition-stub')).toBeInTheDocument()
  })

  it('收起只隐藏不卸载，再展开复用同一取数体（缓存命中，不重新挂载）', () => {
    const button = setupComponent()
    fireEvent.click(button)
    const stub = screen.getByTestId('composition-stub')

    fireEvent.click(screen.getByRole('button', { name: /收起组成视图/ }))
    // 收起：DOM 仍在（query 保持订阅，不因卸载而重拉），只是被 hidden
    expect(screen.getByTestId('composition-stub')).toBe(stub)
    expect(stub.closest('[hidden]')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /展开组成视图/ }))
    expect(screen.getByTestId('composition-stub')).toBe(stub)
    expect(stub.closest('[hidden]')).toBeNull()
  })

  it('详情补拉失败（含容器已软删 404）→ 「组成加载失败」+ 重试，不白屏', () => {
    const retry = vi.fn()
    useContainerCompositionMock.mockReturnValue(
      model({ detailError: true, trace: null, retry })
    )
    const button = setupComponent()
    fireEvent.click(button)

    expect(screen.getByText('组成加载失败')).toBeInTheDocument()
    expect(screen.queryByTestId('composition-stub')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(retry).toHaveBeenCalledTimes(1)
  })
})
