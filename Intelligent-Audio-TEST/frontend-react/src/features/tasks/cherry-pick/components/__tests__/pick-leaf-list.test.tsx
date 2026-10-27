/**
 * 叶明细分页列表测试（INT-1510 §8.2.3 第 4 条 / 接线卡 INT-1819）。
 * 展开节点 → candidates 按「task_ids + case_ids + device_id/api_id + result_type」
 * 服务端分页；`total` 取响应值；翻页换 page 参数，上一页/下一页按 total 收口。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchPageMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/cherry-pick-api', () => ({
  fetchCherryPickCandidatePage: fetchPageMock,
}))

const { PickLeafList } = await import(
  '@/features/tasks/cherry-pick/components/pick-leaf-list'
)

const TREE_FILTER = {
  taskIds: [419],
  caseIds: ['c1'],
  deviceId: 1,
  apiId: null,
  resultType: 'default',
}

function row(n: number) {
  return {
    resultId: n,
    taskId: 419,
    taskName: '任务419',
    caseId: 'c1',
    caseName: null,
    tags: [],
    groupId: null,
    groupName: null,
    totalDuration: null,
    rounds: null,
    deviceId: 1,
    deviceName: null,
    apiId: null,
    apiName: null,
    resultType: 'default',
    algorithmType: null,
    executionStatus: 'completed',
    evaluationStatus: 'pending',
    evaluated: false,
    createdAt: '2026-10-21T09:00:00',
  }
}

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('PickLeafList（叶明细分页）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('首屏按 page=1 / per_page=20 取数，total 取响应值并显示分页条', async () => {
    fetchPageMock.mockResolvedValue({
      items: Array.from({ length: 20 }, (_, i) => row(i + 1)),
      total: 45,
      page: 1,
      perPage: 20,
    })
    render(
      <PickLeafList
        filter={TREE_FILTER}
        selectedIds={new Set()}
        onToggleLeaf={() => {}}
      />,
      { wrapper: wrapper() }
    )

    await waitFor(() => expect(screen.getAllByTestId(/^pick-leaf-/)).toHaveLength(20))
    expect(fetchPageMock).toHaveBeenCalledWith(TREE_FILTER, 1, 20)
    expect(screen.getByText('第 1–20 条 / 共 45 条')).toBeInTheDocument()
    expect(screen.getByText('1 / 3')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '结果行下一页' }))
    await waitFor(() =>
      expect(fetchPageMock).toHaveBeenLastCalledWith(TREE_FILTER, 2, 20)
    )
    expect(await screen.findByText('2 / 3')).toBeInTheDocument()
  })

  it('设备软删渲染「未知设备」、缺 result_type 渲染「结果类型待补充」，不裸显 UUID；叶行不渲染用例名', async () => {
    fetchPageMock.mockResolvedValue({
      items: [row(7)],
      total: 1,
      page: 1,
      perPage: 20,
    })
    render(
      <PickLeafList
        filter={TREE_FILTER}
        selectedIds={new Set()}
        onToggleLeaf={() => {}}
      />,
      { wrapper: wrapper() }
    )
    expect(await screen.findByText('未知设备')).toBeInTheDocument()
    expect(screen.getByText('结果类型待补充')).toBeInTheDocument()
    // INT-2098：叶行不再重复显示用例名（用例名只保留在用例卡）
    expect(screen.queryByText('未知用例')).not.toBeInTheDocument()
  })
})
