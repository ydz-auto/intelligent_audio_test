/**
 * 标签卡片流测试（11_用例域.md §3.6）：
 * 审计 P3-1 移动端（≤640px）子视图切换收进「显示方式」下拉——组头不渲染 Tabs，
 * 下拉选择「按用例分组」后客户端聚合（分组子组头 + 未分组桶）。
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
import { TagCaseList } from '@/features/testcases/components/tag-case-list'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'

const CASES: TestCaseListItem[] = [
  { id: 'tc-001', name: '智能音箱-播放音乐', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: ['音箱'], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 156, rounds: 2 },
  { id: 'tc-002', name: '智能音箱-调节音量', description: null, groupId: null, groupName: null, type: 'e2e', tags: ['音箱'], algorithmType: 'asr-v3', createdAt: '2026-09-11 09:00', updatedAt: '2026-10-14 16:20', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 48, rounds: 1 },
  { id: 'tc-003', name: '车载-导航指令', description: null, groupId: 'g2', groupName: '车载语音交互', type: 'e2e', tags: ['中文'], algorithmType: 'asr-v3', createdAt: '2026-09-15 09:00', updatedAt: '2026-10-12 15:10', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 96, rounds: 2 },
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

/** 测试内覆盖 matchMedia 模拟移动端视口（≤640px；审计 P3-1），并随测试结束还原 */
const ORIGINAL_MATCH_MEDIA = window.matchMedia
function mockMobile(active: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string): MediaQueryList => ({
      matches:
        query.includes('prefers-reduced-motion') ||
        (active && query.includes('max-width: 640px')),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
}
function restoreMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: ORIGINAL_MATCH_MEDIA,
  })
}

function Harness({ cases = CASES }: { cases?: TestCaseListItem[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  return (
    <QueryClientProvider client={queryClient}>
      <TagCaseList
        cases={cases}
        loading={false}
        selected={selected}
        tagRegistry={MOCK_TAGS as TagItem[]}
        callbacks={noopCallbacks}
        onCreate={vi.fn()}
        onToggleSelect={(id, c) =>
          setSelected((prev) => {
            const next = new Set(prev)
            if (c) next.add(id)
            else next.delete(id)
            return next
          })
        }
        onToggleAll={(ids, c) =>
          setSelected((prev) => {
            const next = new Set(prev)
            ids.forEach((id) => (c ? next.add(id) : next.delete(id)))
            return next
          })
        }
      />
    </QueryClientProvider>
  )
}

describe('TagCaseList', () => {
  beforeEach(() => {
    useSessionMap.setState({ groupSubView: {}, tagSubView: {} })
  })

  it('桌面端渲染 Tabs 胶囊「平铺｜按用例分组」', () => {
    render(<Harness />)
    expect(screen.getAllByRole('tab').length).toBeGreaterThan(0)
    expect(screen.getAllByText('按用例分组').length).toBeGreaterThan(0)
  })

  it('审计 P3-1：移动端（≤640px）组头不渲染 Tabs，子视图切换收进「显示方式」下拉', async () => {
    mockMobile(true)
    try {
      const user = userEvent.setup()
      render(<Harness />)
      // Tabs 胶囊不渲染
      expect(screen.queryAllByRole('tab')).toHaveLength(0)
      // 默认收起 → 先展开第一个标签卡「音箱」（分组子组头/未分组桶在标签组内内容区）
      await user.click(screen.getAllByText('音箱')[0])
      // 「显示方式」下拉触发钮存在（每个标签卡一枚，取第一个「音箱」卡）
      await user.click(screen.getAllByRole('button', { name: '显示方式' })[0])
      expect(await screen.findByText('按用例分组')).toBeInTheDocument()
      // 选择「按用例分组」→ 标签内按分组客户端聚合（分组子组头 + 未分组桶）
      await user.click(screen.getByText('按用例分组'))
      expect(await screen.findByText('智能音箱功能测试')).toBeInTheDocument()
      expect(screen.getByText('未分组')).toBeInTheDocument()
    } finally {
      restoreMatchMedia()
    }
  })

  it('INT-1970：列表头「全选用例」传 filtered 回调时按筛选全量圈定（按标签视图同口径）', async () => {
    const user = userEvent.setup()
    const onToggleAll = vi.fn()
    const onToggleAllFiltered = vi.fn()
    render(
      <QueryClientProvider client={queryClient}>
        <TagCaseList
          cases={CASES}
          loading={false}
          selected={new Set()}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onCreate={vi.fn()}
          onToggleAll={onToggleAll}
          onToggleAllFiltered={onToggleAllFiltered}
          allFilteredSelected={false}
        />
      </QueryClientProvider>
    )
    await user.click(screen.getByLabelText('全选用例'))
    expect(onToggleAllFiltered).toHaveBeenCalledWith(true)
    expect(onToggleAll).not.toHaveBeenCalled()
  })

  it('INT-1970：勾选态取 allFilteredSelected，已加载页全选但筛选总数更大时不显示全选', () => {
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <TagCaseList
          cases={CASES}
          loading={false}
          selected={new Set(CASES.map((c) => c.id))}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onCreate={vi.fn()}
          onToggleAll={vi.fn()}
          onToggleAllFiltered={vi.fn()}
          allFilteredSelected={false}
        />
      </QueryClientProvider>
    )
    expect(screen.getByLabelText('全选用例')).toHaveAttribute('aria-checked', 'false')
    rerender(
      <QueryClientProvider client={queryClient}>
        <TagCaseList
          cases={CASES}
          loading={false}
          selected={new Set(CASES.map((c) => c.id))}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onCreate={vi.fn()}
          onToggleAll={vi.fn()}
          onToggleAllFiltered={vi.fn()}
          allFilteredSelected
        />
      </QueryClientProvider>
    )
    expect(screen.getByLabelText('全选用例')).toHaveAttribute('aria-checked', 'true')
  })
})
