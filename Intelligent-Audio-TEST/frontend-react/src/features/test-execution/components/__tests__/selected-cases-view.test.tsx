/**
 * 步骤一「只显示已选中」视图（10_测试执行.md §3.5 选择态复核）。
 * 保护：按分组/按标签聚合只呈现传入的已选用例；被当前筛选排除的已选条数显式提示；
 * 取消勾选回调；尚未勾选与筛选排除两类空态文案；取数失败给错误态 + 重试。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { SelectedCasesView } from '@/features/test-execution/components/selected-cases-view'
import { SELECTED_ONLY_COPY } from '@/features/test-execution/constants'

const CASES: TestCaseListItem[] = [
  {
    id: 'tc-001',
    name: '智能音箱-播放音乐',
    description: null,
    groupId: 'g1',
    groupName: '智能音箱功能测试',
    tags: ['音箱'],
    algorithmType: 'asr-v3',
    createdAt: '2026-09-10 10:00',
    updatedAt: '2026-10-15 09:32',
    isFavorite: false,
    deleted: false,
    deletedAt: null,
    deletedByUserId: null,
    totalDuration: 156,
    rounds: 2,
  },
  {
    id: 'tc-002',
    name: '车载-导航指令',
    description: null,
    groupId: null,
    groupName: null,
    tags: ['中文'],
    algorithmType: 'asr-v3',
    createdAt: '2026-09-15 09:00',
    updatedAt: '2026-10-12 15:10',
    isFavorite: false,
    deleted: false,
    deletedAt: null,
    deletedByUserId: null,
    totalDuration: 96,
    rounds: 2,
  },
]

const TAGS: TagItem[] = [
  {
    id: 1,
    name: '音箱',
    description: null,
    color: '#3b82f6',
    categoryId: null,
    categoryName: '设备',
    createdAt: null,
    updatedAt: null,
  },
  {
    id: 2,
    name: '中文',
    description: null,
    color: null,
    categoryId: null,
    categoryName: null,
    createdAt: null,
    updatedAt: null,
  },
]

const noopCallbacks: CaseCardCallbacks = {
  onPreview: vi.fn(),
  onCopy: vi.fn(),
  onFavorite: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onRestore: vi.fn(),
  onPurge: vi.fn(),
}

/** 算法名映射走真实 GET /algorithm/options 的 query 缓存（CaseCard 读 useQuery） */
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: 0 } },
})
queryClient.setQueryData(['shell', 'algorithm', 'options'], [
  { value: 'asr-v3', name: '通用识别引擎' },
])

function renderView(ui: ReactElement) {
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const GROUPS: TestCaseGroup[] = [
  {
    id: 'g1',
    name: '智能音箱功能测试',
    description: null,
    algorithmType: null,
    createdAt: '2026-09-01 10:00',
    updatedAt: '2026-10-15 09:32',
    testCaseCount: 8,
    totalDuration: 600,
  },
]

const baseProps = {
  cases: CASES,
  loading: false,
  isError: false,
  onRetry: vi.fn(),
  onExit: vi.fn(),
  selectedCount: CASES.length,
  tagRegistry: TAGS,
  callbacks: noopCallbacks,
  allGroups: GROUPS,
  filters: {},
  trash: false,
  onBatchAction: vi.fn(),
}

describe('SelectedCasesView 只显示已选中', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('按标签视图：标签组头 + 已选用例卡（未传入的用例不出现）', () => {
    renderView(<SelectedCasesView {...baseProps} view='by-tag' />)

    // 标签名同时出现在组头与用例卡标签徽章上
    expect(screen.getAllByText('音箱').length).toBeGreaterThan(0)
    expect(screen.getAllByText('中文').length).toBeGreaterThan(0)
    expect(screen.getByText('智能音箱-播放音乐')).toBeInTheDocument()
    expect(screen.getByText('车载-导航指令')).toBeInTheDocument()
    expect(screen.getByText(SELECTED_ONLY_COPY.title)).toBeInTheDocument()
    expect(
      screen.getByText(new RegExp(`按标签 · ${SELECTED_ONLY_COPY.summary(2)}`))
    ).toBeInTheDocument()
  })

  it('按分组视图：复用原分组卡，展开后才显示该组已选用例', async () => {
    renderView(<SelectedCasesView {...baseProps} view='by-group' />)

    // 真实分组沿用用例管理页分组卡（含更新于/计数）；未分组桶仍用只读组头
    expect(screen.getByText('智能音箱功能测试')).toBeInTheDocument()
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.getByText(/更新于/)).toBeInTheDocument()
    // 折叠态不渲染该组用例卡（避免「一堆卡片」）
    expect(screen.queryByText('智能音箱-播放音乐')).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('智能音箱功能测试'))
    expect(screen.getByText('智能音箱-播放音乐')).toBeInTheDocument()
    expect(screen.getByText('车载-导航指令')).toBeInTheDocument()
  })

  it('已选用例被当前筛选排除时显式提示条数', () => {
    renderView(
      <SelectedCasesView {...baseProps} view='by-group' selectedCount={5} />
    )

    expect(
      screen.getByText(SELECTED_ONLY_COPY.hiddenByFilter(3))
    ).toBeInTheDocument()
  })

  it('取消勾选已选用例卡回调 onToggleSelect(id, false)', async () => {
    const onToggleSelect = vi.fn()
    renderView(
      <SelectedCasesView
        {...baseProps}
        view='by-tag'
        onToggleSelect={onToggleSelect}
      />
    )

    await userEvent.click(
      screen.getByRole('checkbox', { name: '选择 智能音箱-播放音乐' })
    )
    expect(onToggleSelect).toHaveBeenCalledWith('tc-001', false)
  })

  it('尚未勾选任何用例：空态 +「查看全部用例」关闭视图', async () => {
    const onExit = vi.fn()
    renderView(
      <SelectedCasesView
        {...baseProps}
        view='by-group'
        cases={[]}
        selectedCount={0}
        onExit={onExit}
      />
    )

    expect(screen.getByText(SELECTED_ONLY_COPY.emptyTitle)).toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: SELECTED_ONLY_COPY.exit })
    )
    expect(onExit).toHaveBeenCalledTimes(1)
  })

  it('已选用例全被筛选排除：区分「筛选无命中」空态文案', () => {
    renderView(
      <SelectedCasesView
        {...baseProps}
        view='by-group'
        cases={[]}
        selectedCount={2}
      />
    )

    expect(
      screen.getByText(SELECTED_ONLY_COPY.emptyFilteredTitle)
    ).toBeInTheDocument()
  })

  it('取数失败且无可展示数据：错误态 + 重试', async () => {
    const onRetry = vi.fn()
    renderView(
      <SelectedCasesView
        {...baseProps}
        view='by-tag'
        cases={[]}
        selectedCount={2}
        isError
        onRetry={onRetry}
      />
    )

    expect(screen.getByText('已选用例加载失败')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
