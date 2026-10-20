/**
 * 分组卡片流测试（V9.7.10 TestCaseListContainer 分组视图等价移植，11_用例域.md §3.5）：
 * INT-1027 回归——groups 异步加载后分组卡默认收起（组头可见、组内用例需点击展开）；
 * 组头勾选全选/全不选；组内懒加载「已显示 {n} / {总} 条 · 加载更多」。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'

import { useSessionMap } from '@/application/testcases/use-session-map'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import { MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'
import { GroupedCaseList } from '@/features/testcases/components/grouped-case-list'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'

const GROUPS: TestCaseGroup[] = [
  {
    id: 'g1',
    name: '智能音箱功能测试',
    description: null,
    algorithmType: 'asr-v3',
    createdAt: '2026-09-01 11:00',
    updatedAt: '2026-10-14 16:20',
    testCaseCount: 5,
  },
  {
    id: 'g2',
    name: '车载语音交互',
    description: null,
    algorithmType: 'asr-v3',
    createdAt: '2026-09-02 09:30',
    updatedAt: '2026-10-12 15:10',
    testCaseCount: 3,
  },
]

const CASES: TestCaseListItem[] = [
  { id: 'tc-001', name: '智能音箱-播放音乐', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: ['音箱'], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 156, rounds: 2 },
  { id: 'tc-002', name: '智能音箱-调节音量', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-11 09:00', updatedAt: '2026-10-14 16:20', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 48, rounds: 1 },
  { id: 'tc-003', name: '智能音箱-语音点歌', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: [], algorithmType: 'asr-stream', createdAt: '2026-09-12 14:00', updatedAt: '2026-10-14 10:05', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 210, rounds: 3 },
  { id: 'tc-004', name: '智能音箱-天气查询', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-13 10:30', updatedAt: '2026-10-13 09:50', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 12, rounds: 1 },
  { id: 'tc-005', name: '智能音箱-闹钟设置', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-14 08:00', updatedAt: '2026-10-12 11:30', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 132, rounds: 2 },
  { id: 'tc-006', name: '智能音箱-闹钟设置2', description: null, groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-14 08:00', updatedAt: '2026-10-12 11:30', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 130, rounds: 2 },
  { id: 'tc-007', name: '车载-导航指令', description: null, groupId: 'g2', groupName: '车载语音交互', type: 'e2e', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-15 09:00', updatedAt: '2026-10-12 15:10', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 96, rounds: 2 },
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

const actionCallbacks = {
  onCreateInGroup: vi.fn(),
  onEditGroup: vi.fn(),
  onDeleteGroup: vi.fn(),
  onCopyGroup: vi.fn(),
}

const setupUser = () => userEvent.setup()

/** React Query 上下文（useIsFetching §3.3.3 降透明度依赖，INT-595 补） */
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

/** 受控外壳：模拟 React Query 异步返回 groups（首帧空数组，加载后补齐） */
function Harness({
  loading = false,
  cases = CASES,
  trash = false,
  hasQueryFilters = false,
}: {
  loading?: boolean
  cases?: TestCaseListItem[]
  trash?: boolean
  hasQueryFilters?: boolean
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  return (
    <QueryClientProvider client={queryClient}>
      <GroupedCaseList
        groups={loading ? [] : GROUPS}
        cases={loading ? [] : cases}
        loading={loading}
        trash={trash}
        hasQueryFilters={hasQueryFilters}
        selected={selected}
        tagRegistry={MOCK_TAGS as TagItem[]}
        callbacks={noopCallbacks}
        onBatchAction={vi.fn()}
        actionCallbacks={actionCallbacks}
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

describe('GroupedCaseList', () => {
  beforeEach(() => {
    // 会话级 per-card 子视图状态复位（用例间隔离）
    useSessionMap.setState({ groupSubView: {}, tagSubView: {} })
  })

  it('INT-1027：分组异步到达后默认收起，组头可展开、组内用例点击后可见', async () => {
    const user = setupUser()
    const { rerender } = render(<Harness loading />)
    // 首帧 groups 为空（React Query 未返回）→ 骨架态
    expect(screen.queryByText('智能音箱功能测试')).not.toBeInTheDocument()
    // 分组到达后默认收起：组头可见，组内用例卡不可见
    rerender(<Harness />)
    await waitFor(() => {
      expect(screen.getByText('智能音箱功能测试')).toBeInTheDocument()
    })
    expect(screen.queryByText('智能音箱-播放音乐')).not.toBeInTheDocument()
    expect(screen.queryByText('车载-导航指令')).not.toBeInTheDocument()
    // 点组头展开后组内用例可见；另一个组保持收起
    await user.click(screen.getByText('智能音箱功能测试'))
    expect(screen.getByText('智能音箱-播放音乐')).toBeInTheDocument()
    expect(screen.queryByText('车载-导航指令')).not.toBeInTheDocument()
    await user.click(screen.getByText('车载语音交互'))
    expect(screen.getByText('车载-导航指令')).toBeInTheDocument()
  })

  it('加载态渲染骨架而非分组头', () => {
    render(<Harness loading />)
    expect(screen.queryByText('智能音箱功能测试')).not.toBeInTheDocument()
  })

  it('组头勾选全选该组用例，页级计数联动', async () => {
    const user = setupUser()
    render(<Harness />)
    await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
    // g1 共 6 条全选，列表头「已选择 6 个用例」
    expect(screen.getByText('已选择 6 个用例')).toBeInTheDocument()
  })

  it('组内懒加载分页：超过 5 条显示「已显示 5 / 6 条 · 加载更多」，点击后全部可见', async () => {
    const user = setupUser()
    render(<Harness />)
    // 默认收起 → 先展开 g1 分组卡
    await user.click(screen.getByText('智能音箱功能测试'))
    // 第 6 条初始不可见
    expect(screen.queryByText('智能音箱-闹钟设置2')).not.toBeInTheDocument()
    expect(screen.getByText(/已显示 5 \/ 6 条 · 加载更多/)).toBeInTheDocument()
    await user.click(screen.getByText(/加载更多/))
    // 点击后加载第 6 条，加载更多行消失
    expect(screen.getByText('智能音箱-闹钟设置2')).toBeInTheDocument()
    expect(screen.queryByText(/已显示 6 \/ 6 条 · 加载更多/)).not.toBeInTheDocument()
  })

  it('分组排序下拉：按用例数量/分组名称/创建时间', async () => {
    const user = setupUser()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: /排序/ }))
    expect(await screen.findByText('按用例数量')).toBeInTheDocument()
    expect(screen.getByText('按分组名称')).toBeInTheDocument()
    expect(screen.getByText('按创建时间')).toBeInTheDocument()
  })

  it('INT-584 子视图切换：默认平铺；切「按标签」客户端聚合（标签子组 + 未设置标签桶，per-card 会话保留）', async () => {
    const user = setupUser()
    render(<Harness />)
    // 默认收起 → 展开两个分组卡（组头子视图切换钮与组内内容均需可见）
    await user.click(screen.getByText('智能音箱功能测试'))
    await user.click(screen.getByText('车载语音交互'))
    // 默认态 = 平铺：用例卡直接渲染，无子分组头
    expect(screen.getByText('智能音箱-播放音乐')).toBeInTheDocument()
    expect(screen.queryByText('未设置标签')).not.toBeInTheDocument()
    // 点击第一个分组卡（g1）组头的「按标签」切换
    const toggles = screen.getAllByText('按标签')
    await user.click(toggles[0])
    // g1 可见用例含 tc-001（音箱）与 4 条无标签 → 标签子组「音箱」（组头 + 卡内 TagBadge 多处出现）
    // + 末尾「未设置标签」桶
    expect(screen.getAllByText('音箱').length).toBeGreaterThan(0)
    expect(screen.getByText('未设置标签')).toBeInTheDocument()
    // g2 分组卡仍为平铺（per-card 状态独立）：其组内用例无子分组头
    expect(screen.getByText('车载-导航指令')).toBeInTheDocument()
  })

  it('INT-584 子视图空态：组内可见用例全部无标签时显示空态，切换控件保持选中', async () => {
    const user = setupUser()
    useSessionMap.getState().setGroupSubView('g2', 'byTag')
    render(<Harness />)
    // 默认收起 → 先展开 g2 分组卡（空态在组内内容区）
    await user.click(screen.getByText('车载语音交互'))
    // g2 用例全部无标签 → 按标签子视图空态
    expect(screen.getByText('该分组下用例均未设置标签')).toBeInTheDocument()
    expect(screen.getByText('切换回「平铺」可查看该分组全部用例')).toBeInTheDocument()
    // 切换控件保持「按标签」选中态（不自动跳变）
    expect(screen.getAllByText('按标签').length).toBeGreaterThan(0)
  })

  it('审计 P3-1：移动端（≤640px）组头不渲染 Tabs，子视图切换收进 CaseGroupActions 下拉首项「显示方式」', async () => {
    mockMobile(true)
    try {
      const user = setupUser()
      render(<Harness />)
      // Tabs 胶囊不渲染（组头空间收紧）
      expect(screen.queryAllByRole('tab')).toHaveLength(0)
      // 默认收起 → 先展开 g1（「未设置标签」桶在组内内容区）
      await user.click(screen.getByText('智能音箱功能测试'))
      // 打开第一个分组卡（g1）的「批量修改」下拉 → 首项「显示方式」子菜单
      await user.click(screen.getAllByRole('button', { name: /批量修改/ })[0])
      // base-ui 子菜单触发器 hover 展开；jsdom 指针几何为零，子项点击用 fireEvent（绕过 pointer-events 守卫）
      await user.hover(await screen.findByText('显示方式'))
      await screen.findByText('按标签')
      fireEvent.click(screen.getByText('按标签'))
      // 选择「按标签」→ g1 按标签客户端聚合（「未设置标签」桶出现）
      expect(screen.getByText('未设置标签')).toBeInTheDocument()
    } finally {
      restoreMatchMedia()
    }
  })

  it('INT-595 空态补：筛选排除全部用例时分页区不再空白，显「没有找到符合条件的测试用例」', () => {
    render(<Harness cases={[]} />)
    expect(screen.getByText('没有找到符合条件的测试用例')).toBeInTheDocument()
    expect(screen.getByText('尝试清空「分组」「标签」筛选')).toBeInTheDocument()
    // 空态下仍提供「+ 新增用例」入口
    expect(screen.getByRole('button', { name: /新增用例/ })).toBeInTheDocument()
  })

  it('INT-595 空态补：回收站空态文案「回收站为空」且不出现新增入口', () => {
    render(<Harness cases={[]} trash />)
    expect(screen.getByText('回收站为空')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /新增用例/ })).not.toBeInTheDocument()
  })

  it('INT-595 空态补：回收站态筛选无匹配时区分「筛选无匹配」而非「回收站为空」', () => {
    render(<Harness cases={[]} trash hasQueryFilters />)
    expect(screen.getByText('没有找到符合条件的回收站用例')).toBeInTheDocument()
    expect(screen.getByText('尝试清空「分组」「标签」等筛选条件')).toBeInTheDocument()
    expect(screen.queryByText('回收站为空')).not.toBeInTheDocument()
  })
})
