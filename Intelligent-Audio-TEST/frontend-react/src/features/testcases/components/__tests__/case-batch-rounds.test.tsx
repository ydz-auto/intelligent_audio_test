/**
 * 批量设置评估维度 × 轮次登记表（INT-1506 审返 P2 回归）。
 *
 * 缺陷背景：轮次只从列表首页 items 推导时，分组视图里选中的用例（来自按分组懒加载的分页、
 * 与首页 100 条无交集）会被判成「轮次未知」，弹窗给出「所选用例暂无可配置的轮次信息」假空态
 * 并禁用「确定」。
 * 本测试按页面装配：GroupedCaseList + CaseBatchActionsHost 同挂在 CaseRoundsProvider 下，
 * 首页 items 故意不含组内用例；展开分组 → 组头「批量修改 → 评价维度」→ 轮次页签按组内用例
 * 自身 rounds 渲染、确定可点。未登记的选中用例只提示「尚未加载」，不当成「无轮次」。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSessionMap } from '@/application/testcases/use-session-map'
import { CaseRoundsProvider } from '@/application/testcases/case-rounds-registry'
import type { BatchDialogState } from '@/application/testcases/use-case-batch-actions'
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import { CaseBatchActionsHost } from '@/features/testcases/components/case-batch-actions-host'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { GroupedCaseList } from '@/features/testcases/components/grouped-case-list'
import { MOCK_CASE_DIMENSIONS, MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'

const { GROUPS, GROUP_CASES, PAGE_ITEMS } = vi.hoisted(() => {
  const GROUPS: TestCaseGroup[] = [
    {
      id: 'g1',
      name: '拒识',
      description: null,
      algorithmType: 'asr-v3',
      createdAt: '2026-09-01 11:00',
      updatedAt: '2026-10-14 16:20',
      testCaseCount: 3,
    },
  ]
  const GROUP_CASES: TestCaseListItem[] = [
    { id: 'grp-1', name: '拒识-1', description: null, groupId: 'g1', groupName: '拒识', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 60, rounds: 3 },
    { id: 'grp-2', name: '拒识-2', description: null, groupId: 'g1', groupName: '拒识', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 60, rounds: 2 },
    { id: 'grp-3', name: '拒识-3', description: null, groupId: 'g1', groupName: '拒识', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 60, rounds: 1 },
  ]
  /** 列表首页 items：只含其他分组的用例，与组内用例 id 无交集（真实库 581 条时的分组视图口径） */
  const PAGE_ITEMS: TestCaseListItem[] = [
    { id: 'page-1', name: '首页用例', description: null, groupId: 'g9', groupName: '其他分组', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 60, rounds: 4 },
  ]
  return { GROUPS, GROUP_CASES, PAGE_ITEMS }
})

vi.mock('@/infrastructure/api/testcases-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/testcases-api')>()
  return {
    ...actual,
    fetchTestCasesByGroup: vi.fn(async (groupId: string, _filters: unknown, page = 1, perPage = 20) => {
      const matched = GROUP_CASES.filter((c) => c.groupId === groupId)
      return {
        items: matched.slice((page - 1) * perPage, page * perPage),
        total: matched.length,
      }
    }),
  }
})
vi.mock('@/infrastructure/api/testcases-ids-api', () => ({
  fetchCaseIdsByFilter: vi.fn(async () => ({ ids: GROUP_CASES.map((c) => c.id), total: GROUP_CASES.length })),
}))

/**
 * base-ui Tabs 内部走 `#prehydration/tabs/indicator` 子路径，vitest 外部化依赖下 jsdom 解析不到
 * （与既有测试同口径：不加载真实 Tabs）。本测试只关心批量弹窗轮次，视图页签用轻量替身。
 */
vi.mock('@/components/ui/tabs', () => {
  const Stub = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  return { Tabs: Stub, TabsList: Stub, TabsTrigger: Stub, TabsContent: Stub }
})

const noopCallbacks: CaseCardCallbacks = {
  onPreview: vi.fn(),
  onCopy: vi.fn(),
  onFavorite: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onRestore: vi.fn(),
  onPurge: vi.fn(),
}
const actionCallbacks = {
  onCreateInGroup: vi.fn(),
  onEditGroup: vi.fn(),
  onDeleteGroup: vi.fn(),
  onCopyGroup: vi.fn(),
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: 0 } },
})

/** 页面装配：分组列表 + 批量弹窗宿主同挂在轮次登记表下（页级 items 不含组内用例） */
function PageHarness() {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [batchDialog, setBatchDialog] = useState<BatchDialogState | null>(null)
  const filters: TestCaseListFilters = {}
  return (
    <QueryClientProvider client={queryClient}>
      <CaseRoundsProvider cases={PAGE_ITEMS}>
        <GroupedCaseList
          groups={GROUPS}
          cases={PAGE_ITEMS}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={filters}
          selected={selected}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          actionCallbacks={actionCallbacks}
          onBatchAction={(action, ids) => {
            if (action === 'dimensions') {
              setBatchDialog({ kind: 'dimensions', count: ids.length, ids })
            }
          }}
          onToggleSelect={(id, checked) =>
            setSelected((prev) => {
              const next = new Set(prev)
              if (checked) next.add(id)
              else next.delete(id)
              return next
            })
          }
          onToggleAll={(ids, checked) =>
            setSelected((prev) => {
              const next = new Set(prev)
              ids.forEach((id) => (checked ? next.add(id) : next.delete(id)))
              return next
            })
          }
        />
        <CaseBatchActionsHost
          batchDialog={batchDialog}
          setBatchDialog={setBatchDialog}
          confirm={null}
          setConfirm={() => {}}
          handleConfirm={() => {}}
          groups={GROUPS}
          tags={[]}
          dimensions={MOCK_CASE_DIMENSIONS}
        />
      </CaseRoundsProvider>
    </QueryClientProvider>
  )
}

/** 宿主单测：选中 id 全部未登记（列表尚未加载） */
function UnknownHostHarness() {
  const [batchDialog, setBatchDialog] = useState<BatchDialogState | null>({
    kind: 'dimensions',
    count: 2,
    ids: ['grp-1', 'grp-2'],
  })
  return (
    <CaseRoundsProvider cases={PAGE_ITEMS}>
      <CaseBatchActionsHost
        batchDialog={batchDialog}
        setBatchDialog={setBatchDialog}
        confirm={null}
        setConfirm={() => {}}
        handleConfirm={() => {}}
        groups={GROUPS}
        tags={[]}
        dimensions={MOCK_CASE_DIMENSIONS}
      />
    </CaseRoundsProvider>
  )
}

describe('批量设置评估维度：轮次按选中用例自身 rounds（INT-1506 审返 P2）', () => {
  beforeEach(() => {
    useSessionMap.setState({ groupSubView: {}, tagSubView: {} })
    queryClient.clear()
  })

  it('选中用例来自分组懒加载（不在首页 items）时，轮次页签按组内用例 rounds 渲染且确定可点', async () => {
    const user = userEvent.setup()
    render(<PageHarness />)

    // 展开分组 → 组内用例懒加载（这些 id 不在首页 items）
    await user.click(await screen.findByText('拒识'))
    expect(await screen.findByText('拒识-1')).toBeInTheDocument()

    // 组头「批量修改 → 评价维度」（无勾选时作用于组内已加载用例）
    await user.click(screen.getByRole('button', { name: /拒识 批量修改/ }))
    await user.click(await screen.findByText('评价维度'))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('您勾选了 3 个用例')
    // 不是假空态；确定可点
    expect(screen.queryByText('所选用例暂无可配置的轮次信息')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确定' })).toBeEnabled()

    // 逐轮档位按组内用例最大轮次 3 渲染（不出现第 4 轮，也不为空）
    await user.click(screen.getByRole('radio', { name: '逐轮设置（每轮可不同）' }))
    expect(await screen.findByRole('button', { name: '第 1 轮' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第 3 轮' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '第 4 轮' })).not.toBeInTheDocument()
  })

  it('选中用例轮次未登记时显式提示「尚未加载」，仍可按所有轮次提交（不当成无轮次）', async () => {
    render(<UnknownHostHarness />)
    const dialog = await screen.findByRole('dialog')
    expect(dialog).not.toHaveTextContent('所选用例暂无可配置的轮次信息')
    expect(screen.getByTestId('batch-dim-rounds-unknown')).toHaveTextContent(
      '其中 2 个用例的轮次信息尚未加载'
    )
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '确定' })).toBeEnabled()
    )
    // 没有已知轮次时，按轮次的两档不可用
    expect(screen.getByRole('radio', { name: '指定轮次（统一设置）' })).toBeDisabled()
    expect(screen.getByRole('radio', { name: '逐轮设置（每轮可不同）' })).toBeDisabled()
  })
})
