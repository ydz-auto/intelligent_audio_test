/**
 * 用例列表查询失败态测试（INT-1605，与 INT-1560 标签页 / INT-1583 音频页同型）。
 * 口径：接口失败不得渲染成「没有找到符合条件的测试用例」/「没有找到标签分组的测试用例」空态——
 * 首屏失败（无旧数据）给整块错误态 + 重试；失败但有上一次结果时保留旧列表 + 行内提示 + 重试；
 * 仅在无错误且无数据时才渲染原空态。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'

import { useSessionMap } from '@/application/testcases/use-session-map'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'
import { MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'
import { GroupedCaseList } from '@/features/testcases/components/grouped-case-list'
import { TagCaseList } from '@/features/testcases/components/tag-case-list'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'

const CASES: TestCaseListItem[] = [
  {
    id: 'tc-001',
    name: '智能音箱-播放音乐',
    description: null,
    groupId: null,
    groupName: null,
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: 0 } },
})

function Harness({
  kind,
  cases,
  isError,
  onRetry,
}: {
  kind: 'group' | 'tag'
  cases: TestCaseListItem[]
  isError?: boolean
  onRetry?: () => void
}) {
  const [selected] = useState<Set<string>>(new Set())
  return (
    <QueryClientProvider client={queryClient}>
      {kind === 'group' ? (
        <GroupedCaseList
          groups={[]}
          cases={cases}
          loading={false}
          isError={isError}
          onRetry={onRetry}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={selected}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onBatchAction={vi.fn()}
          onToggleSelect={vi.fn()}
          onToggleAll={vi.fn()}
        />
      ) : (
        <TagCaseList
          cases={cases}
          loading={false}
          isError={isError}
          onRetry={onRetry}
          selected={selected}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onCreate={vi.fn()}
          onToggleSelect={vi.fn()}
          onToggleAll={vi.fn()}
        />
      )}
    </QueryClientProvider>
  )
}

describe('用例列表查询失败态（INT-1605）', () => {
  beforeEach(() => {
    useSessionMap.setState({ groupSubView: {}, tagSubView: {} })
    queryClient.clear()
  })

  it('分组视图首屏失败：显示「用例列表加载失败」+ 重试，不渲染「没有找到符合条件的测试用例」', async () => {
    const onRetry = vi.fn()
    render(<Harness kind='group' cases={[]} isError onRetry={onRetry} />)

    expect(screen.getByText('用例列表加载失败')).toBeInTheDocument()
    expect(screen.getByText('用例列表获取失败，请重试')).toBeInTheDocument()
    expect(screen.queryByText('没有找到符合条件的测试用例')).not.toBeInTheDocument()
    expect(screen.queryByText('尝试清空「分组」「标签」筛选')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('分组视图失败但有上次数据：保留旧列表 + 行内提示 + 重试', async () => {
    const onRetry = vi.fn()
    render(<Harness kind='group' cases={CASES} isError onRetry={onRetry} />)

    expect(screen.getByRole('alert')).toHaveTextContent(
      '用例列表加载失败，当前显示的是上一次加载的数据'
    )
    // 旧数据保留：分组卡仍在（默认收起，用例卡需展开才渲染）
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.queryByText('没有找到符合条件的测试用例')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('标签视图首屏失败：显示「用例列表加载失败」+ 重试，不渲染「没有找到标签分组的测试用例」', () => {
    render(<Harness kind='tag' cases={[]} isError onRetry={vi.fn()} />)

    expect(screen.getByText('用例列表加载失败')).toBeInTheDocument()
    expect(screen.queryByText('没有找到标签分组的测试用例')).not.toBeInTheDocument()
    expect(screen.queryByText('请为测试用例添加标签')).not.toBeInTheDocument()
  })

  it('标签视图失败但有上次数据：保留旧列表 + 行内提示', () => {
    render(<Harness kind='tag' cases={CASES} isError onRetry={vi.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent(
      '用例列表加载失败，当前显示的是上一次加载的数据'
    )
    // 旧数据保留：标签分组卡仍在（默认收起）
    expect(screen.getByText('音箱')).toBeInTheDocument()
    expect(screen.queryByText('没有找到标签分组的测试用例')).not.toBeInTheDocument()
  })

  it('无错误且无数据：仍渲染原空态（错误态不误伤真空库）', () => {
    const { unmount } = render(<Harness kind='group' cases={[]} />)
    expect(screen.getByText('没有找到符合条件的测试用例')).toBeInTheDocument()
    expect(screen.queryByText('用例列表加载失败')).not.toBeInTheDocument()
    unmount()

    render(<Harness kind='tag' cases={[]} />)
    expect(screen.getByText('没有找到标签分组的测试用例')).toBeInTheDocument()
    expect(screen.queryByText('用例列表加载失败')).not.toBeInTheDocument()
  })
})
