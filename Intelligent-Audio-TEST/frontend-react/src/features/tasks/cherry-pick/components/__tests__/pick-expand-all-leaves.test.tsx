/**
 * 「全部展开」不触发叶明细请求（INT-1819 终审 P1 守卫）。
 *
 * 阶段 2 的叶明细按需分页：叶的父级节点展开才挂 `PickLeafList` → 一条 candidates 请求。
 * 「全部展开」只展开树骨架（到叶的父级之上）：真库 2360 个 (case, device/api, result_type)
 * 组合，若一并展开会一次性打出 2360 条并发叶查询（卡面第 7 条禁止假死 / 重复请求）。
 * 本测试锁三件事：① 三视图「全部展开」叶明细请求 = 0；② 单击单个叶的父级 = 1 条分页请求；
 * ③ 骨架节点（用例卡 / 设备 / result_type）该展开的仍然展开，不因跳过叶父级而漏展开。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PickTreeBranch, PickTreeItem } from '@/domain/models/cherryPick'

const fetchPageMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/cherry-pick-api', () => ({
  fetchCherryPickCandidatePage: fetchPageMock,
}))

const { PickCaseOrgList } = await import(
  '@/features/tasks/cherry-pick/components/pick-case-org-list'
)
const { PickTree } = await import(
  '@/features/tasks/cherry-pick/components/pick-tree'
)
const { isLeafParentBranch } = await import('@/domain/lib/pick-candidate-tree')

/** 叶明细过滤口径（叶的父级节点携带；展开时据此分页） */
function leafFilter(caseId: string) {
  return {
    taskIds: [419],
    caseIds: [caseId],
    deviceId: 1,
    apiId: null,
    resultType: 'default',
  }
}

/** 结果行候选行（candidates 分页响应行） */
function row(resultId: number) {
  return {
    resultId,
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

/** 叶的父级 —— result_type 节点（用例视图：用例 → 设备 → result_type） */
const RT_LEAF_PARENT: PickTreeBranch = {
  kind: 'branch',
  key: 'cv-rt:c1:device:1:default',
  level: 'resultType',
  name: '结果类型待补充',
  count: 6,
  resultIds: [1, 2, 3, 4, 5, 6],
  children: [],
  leafFilter: leafFilter('c1'),
}

const DEVICE_BRANCH: PickTreeBranch = {
  kind: 'branch',
  key: 'cv-device:c1:device:1',
  level: 'device',
  name: '未知设备',
  count: 6,
  resultIds: [1, 2, 3, 4, 5, 6],
  children: [RT_LEAF_PARENT],
}

/** 用例视图顶层用例卡（非叶的父级：children = 设备分支） */
const CASE_VIEW_TOP: PickTreeBranch = {
  kind: 'branch',
  key: 'pcase:c1',
  level: 'case',
  name: '用例 c1',
  caseId: 'c1',
  count: 6,
  resultIds: [1, 2, 3, 4, 5, 6],
  children: [DEVICE_BRANCH],
}

/** 叶的父级 —— 用例节点（设备/结果类型视图：设备 → result_type → 用例） */
const CASE_LEAF_PARENT: PickTreeBranch = {
  kind: 'branch',
  key: 'dv-case:device:1:default:c1',
  level: 'case',
  name: '用例 c1',
  caseId: 'c1',
  count: 6,
  resultIds: [1, 2, 3, 4, 5, 6],
  children: [],
  leafFilter: leafFilter('c1'),
}

/** 设备视图树（设备 → result_type → 用例(叶的父级)） */
const DEVICE_VIEW: PickTreeBranch[] = [
  {
    kind: 'branch',
    key: 'dv-device:device:1',
    level: 'device',
    name: '未知设备',
    count: 6,
    resultIds: [1, 2, 3, 4, 5, 6],
    children: [
      {
        kind: 'branch',
        key: 'dv-rt:device:1:default',
        level: 'resultType',
        name: '结果类型待补充',
        count: 6,
        resultIds: [1, 2, 3, 4, 5, 6],
        children: [CASE_LEAF_PARENT],
      },
    ],
  },
]

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

/** 让潜在的叶明细请求有机会发出（负向断言前先空跑一轮微任务 + 定时器） */
async function settle() {
  await act(async () => {
    await Promise.resolve()
  })
}

describe('「全部展开」不触发叶明细请求（INT-1819 P1 守卫）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchPageMock.mockResolvedValue({
      items: [row(1)],
      total: 1,
      page: 1,
      perPage: 20,
    })
  })

  it('用例视图：全部展开只开骨架（用例卡 + 设备行），result_type 叶父级不发 candidates 请求', async () => {
    render(
      <PickCaseOrgList
        branches={[CASE_VIEW_TOP]}
        selectedIds={new Set()}
        onToggleLeaf={() => {}}
        onToggleBranch={() => {}}
        expandSignal={{ all: true, tick: 1 }}
        org='group'
        subView='flat'
        onOrgChange={() => {}}
        onSubViewChange={() => {}}
      />,
      { wrapper }
    )
    // 骨架仍展开：用例卡已开 → 卡内设备行可见
    expect(await screen.findByText('未知设备')).toBeInTheDocument()
    await settle()
    // 叶的父级（result_type 行）保持收起 → 不挂 PickLeafList
    expect(fetchPageMock).not.toHaveBeenCalled()
    expect(screen.queryAllByTestId(/^pick-leaf-/)).toHaveLength(0)
  })

  it('用例视图：单击 result_type 行仍按需分页（1 条请求），结果行渲染', async () => {
    render(
      <PickCaseOrgList
        branches={[CASE_VIEW_TOP]}
        selectedIds={new Set()}
        onToggleLeaf={() => {}}
        onToggleBranch={() => {}}
        expandSignal={{ all: true, tick: 1 }}
        org='group'
        subView='flat'
        onOrgChange={() => {}}
        onSubViewChange={() => {}}
      />,
      { wrapper }
    )
    await screen.findByText('未知设备')
    expect(fetchPageMock).not.toHaveBeenCalled()

    // 骨架已全开，唯一的「展开」按钮就是 result_type 叶父级行
    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    await waitFor(() => expect(fetchPageMock).toHaveBeenCalledTimes(1))
    expect(fetchPageMock).toHaveBeenCalledWith(RT_LEAF_PARENT.leafFilter, 1, 20)
    expect(await screen.findByTestId('pick-leaf-1')).toBeInTheDocument()
  })

  it('设备视图：全部展开开设备 + result_type，用例卡（叶父级）不发 candidates 请求', async () => {
    render(
      <PickTree
        items={DEVICE_VIEW as PickTreeItem[]}
        selectedIds={new Set()}
        onToggleLeaf={() => {}}
        onToggleBranch={() => {}}
        expandSignal={{ all: true, tick: 1 }}
      />,
      { wrapper }
    )
    // 骨架已展开到用例层：用例卡可见（收起态）
    expect(await screen.findByText('用例 c1')).toBeInTheDocument()
    await settle()
    expect(fetchPageMock).not.toHaveBeenCalled()
  })

  it('设备视图：单击用例卡展开按钮按需分页（1 条请求）', async () => {
    render(
      <PickTree
        items={DEVICE_VIEW as PickTreeItem[]}
        selectedIds={new Set()}
        onToggleLeaf={() => {}}
        onToggleBranch={() => {}}
        expandSignal={{ all: true, tick: 1 }}
      />,
      { wrapper }
    )
    await screen.findByText('用例 c1')
    expect(fetchPageMock).not.toHaveBeenCalled()

    // 用例卡（叶父级）展开按钮：骨架已全开，唯一「展开」即该卡片
    fireEvent.click(screen.getByRole('button', { name: '展开' }))
    await waitFor(() => expect(fetchPageMock).toHaveBeenCalledTimes(1))
    expect(fetchPageMock).toHaveBeenCalledWith(CASE_LEAF_PARENT.leafFilter, 1, 20)
  })

  it('叶父级判定：携带 leafFilter 且无子节点（CollectAllKeys 跳过口径同源）', () => {
    expect(isLeafParentBranch(RT_LEAF_PARENT)).toBe(true)
    expect(isLeafParentBranch(CASE_LEAF_PARENT)).toBe(true)
    expect(isLeafParentBranch(CASE_VIEW_TOP)).toBe(false)
    expect(isLeafParentBranch(DEVICE_BRANCH)).toBe(false)
  })
})
