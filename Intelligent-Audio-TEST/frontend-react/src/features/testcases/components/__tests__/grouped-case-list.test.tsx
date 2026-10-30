/**
 * 分组卡片流测试（V9.7.10 TestCaseListContainer 分组视图等价移植，11_用例域.md §3.5）：
 * INT-1027 回归——groups 异步加载后分组卡默认收起（组头可见、组内用例需点击展开）；
 * 组头勾选全选/全不选；组内懒加载分页（按 group_id 懒拉 +「已显示 {n} / {总} 条 · 加载更多」）。
 * INT-1267 回归——分组卡以 /groups 全部分组渲染（空组也渲染、计数用 testCaseCount），
 * 组内用例展开时按组懒加载（Vue fetchCasesByGroup 对位）；组头全选经 /testcases/ids 圈定整组。
 * INT-1267 审计返修回归——P2 组内懒加载/组头全选合并全局算法筛选；P3 未分组哨兵筛选虚拟组承接、
 * 收藏视图组头全选降级为已加载用例。
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
import type { TestCaseListFilters } from '@/application/testcases/use-testcases-list'
import { MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'
import { GroupedCaseList } from '@/features/testcases/components/grouped-case-list'
import type { CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { fetchTestCasesByGroup } from '@/infrastructure/api/testcases-api'
import { fetchCaseIdsByFilter } from '@/infrastructure/api/testcases-ids-api'

/** vi.mock 工厂被提升到模块顶，夹具数据须经 vi.hoisted 定义（否则 TDZ 引用报错） */
const { GROUPS, CASES } = vi.hoisted(() => {
  const GROUPS: TestCaseGroup[] = [
    {
      id: 'g1',
      name: '智能音箱功能测试',
      description: null,
      algorithmType: 'asr-v3',
      createdAt: '2026-09-01 11:00',
      updatedAt: '2026-10-14 16:20',
      testCaseCount: 6,
    },
    {
      id: 'g2',
      name: '车载语音交互',
      description: null,
      algorithmType: 'asr-v3',
      createdAt: '2026-09-02 09:30',
      updatedAt: '2026-10-12 15:10',
      testCaseCount: 1,
    },
    {
      id: 'g3',
      name: '待归档分组',
      description: null,
      algorithmType: null,
      createdAt: '2026-09-03 08:00',
      updatedAt: '2026-10-11 09:00',
      testCaseCount: 0,
    },
  ]
  const CASES: TestCaseListItem[] = [
    { id: 'tc-001', name: '智能音箱-播放音乐', description: null, groupId: 'g1', groupName: '智能音箱功能测试', tags: ['音箱'], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 156, rounds: 2 },
    { id: 'tc-002', name: '智能音箱-调节音量', description: null, groupId: 'g1', groupName: '智能音箱功能测试', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-11 09:00', updatedAt: '2026-10-14 16:20', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 48, rounds: 1 },
    { id: 'tc-003', name: '智能音箱-语音点歌', description: null, groupId: 'g1', groupName: '智能音箱功能测试', tags: [], algorithmType: 'asr-stream', createdAt: '2026-09-12 14:00', updatedAt: '2026-10-14 10:05', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 210, rounds: 3 },
    { id: 'tc-004', name: '智能音箱-天气查询', description: null, groupId: 'g1', groupName: '智能音箱功能测试', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-13 10:30', updatedAt: '2026-10-13 09:50', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 12, rounds: 1 },
    { id: 'tc-005', name: '智能音箱-闹钟设置', description: null, groupId: 'g1', groupName: '智能音箱功能测试', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-14 08:00', updatedAt: '2026-10-12 11:30', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 132, rounds: 2 },
    { id: 'tc-006', name: '智能音箱-闹钟设置2', description: null, groupId: 'g1', groupName: '智能音箱功能测试', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-14 08:00', updatedAt: '2026-10-12 11:30', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 130, rounds: 2 },
    { id: 'tc-007', name: '车载-导航指令', description: null, groupId: 'g2', groupName: '车载语音交互', tags: [], algorithmType: 'asr-v3', createdAt: '2026-09-15 09:00', updatedAt: '2026-10-12 15:10', isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 96, rounds: 2 },
  ]
  return { GROUPS, CASES }
})

/** 组内懒加载按组 mock（真实 fetchTestCasesByGroup 语义：page/per_page 切片 + total） */
vi.mock('@/infrastructure/api/testcases-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/testcases-api')>()
  return {
    ...actual,
    fetchTestCasesByGroup: vi.fn(
      async (groupId: string, _filters: unknown, page = 1, perPage = 20) => {
        const matched = CASES.filter((c) => (c.groupId ?? '__ungrouped__') === groupId)
        return {
          items: matched.slice((page - 1) * perPage, page * perPage),
          total: matched.length,
        }
      }
    ),
    /** INT-2154：搜索命中全量（服务端同样按名称/描述匹配），分组视图据此聚合每组分命中数 */
    fetchAllTestCasesByFilter: vi.fn(async (query: { search?: string }) => {
      const keyword = query.search?.trim() ?? ''
      if (!keyword) return CASES
      return CASES.filter(
        (c) => c.name.includes(keyword) || (c.description ?? '').includes(keyword)
      )
    }),
  }
})

/** 组头全选经 /testcases/ids 圈定整组 ID（真实分组；契约只认 group 分组名，INT-1267 审计 P1 返修） */
vi.mock('@/infrastructure/api/testcases-ids-api', () => ({
  fetchCaseIdsByFilter: vi.fn(async (query: { group?: string }) => {
    const matched = CASES.filter((c) => c.groupName === query.group).map((c) => c.id)
    return { ids: matched, total: matched.length }
  }),
}))

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
  groupsLoading,
  groups,
  cases = CASES,
  trash = false,
  hasQueryFilters = false,
  filters = {},
}: {
  loading?: boolean
  /** 分组列表查询态（INT-1657 用例：分组先到、扁平集仍在加载） */
  groupsLoading?: boolean
  groups?: TestCaseGroup[]
  cases?: TestCaseListItem[]
  trash?: boolean
  hasQueryFilters?: boolean
  filters?: TestCaseListFilters
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  return (
    <QueryClientProvider client={queryClient}>
      <GroupedCaseList
        groups={groups ?? (loading ? [] : GROUPS)}
        cases={loading ? [] : cases}
        loading={loading}
        groupsLoading={groupsLoading}
        trash={trash}
        hasQueryFilters={hasQueryFilters}
        filters={filters}
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
    // 共享 QueryClient 清缓存（组内懒加载 queryKey 跨用例隔离，避免上一用例缓存泄漏）
    queryClient.clear()
    vi.clearAllMocks()
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
    // 点组头展开后组内用例懒加载可见；另一个组保持收起
    await user.click(screen.getByText('智能音箱功能测试'))
    expect(await screen.findByText('智能音箱-播放音乐')).toBeInTheDocument()
    expect(screen.queryByText('车载-导航指令')).not.toBeInTheDocument()
    await user.click(screen.getByText('车载语音交互'))
    expect(await screen.findByText('车载-导航指令')).toBeInTheDocument()
  })

  it('加载态渲染骨架而非分组头', () => {
    render(<Harness loading />)
    expect(screen.queryByText('智能音箱功能测试')).not.toBeInTheDocument()
  })

  it('INT-1657：分组已到位、用例列表仍在加载 → 渲染分组卡 + 加载提示，不显「没有找到」空态', () => {
    render(<Harness loading groupsLoading={false} groups={GROUPS} cases={[]} />)
    // 首屏误判回归：扁平集未到位时不得给空态结论
    expect(screen.queryByText('没有找到符合条件的测试用例')).not.toBeInTheDocument()
    expect(screen.queryByText('尝试清空「分组」「标签」筛选')).not.toBeInTheDocument()
    // 加载态可见（骨架/进度）
    expect(screen.getByRole('status')).toHaveTextContent('用例列表加载中…')
    // INT-1284 口径保留：分组卡立即渲染，计数取 testCaseCount
    expect(screen.getByText('智能音箱功能测试')).toBeInTheDocument()
    expect(screen.getByText('6 条')).toBeInTheDocument()
  })

  it('INT-1657：分组与用例列表均未到位 → 骨架态，不显「没有找到」空态', () => {
    render(<Harness loading groupsLoading groups={[]} />)
    expect(screen.queryByText('没有找到符合条件的测试用例')).not.toBeInTheDocument()
    expect(screen.queryByText('智能音箱功能测试')).not.toBeInTheDocument()
  })

  it('INT-1657：扁平集到位后空态口径不变（加载结束且无用例 → 空态）', () => {
    render(<Harness cases={[]} />)
    expect(screen.getByText('没有找到符合条件的测试用例')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('INT-1267：/groups 空组也渲染，组头计数用 testCaseCount', async () => {
    render(<Harness />)
    // 空组（testCaseCount=0）同样渲染分组卡 + 0 条徽章
    expect(screen.getByText('待归档分组')).toBeInTheDocument()
    expect(screen.getByText('0 条')).toBeInTheDocument()
    // 展开空组 → 组内懒加载返回空 → 空态文案
    const user = setupUser()
    await user.click(screen.getByText('待归档分组'))
    expect(await screen.findByText('该分组暂无用例')).toBeInTheDocument()
  })

  it('组头勾选全选该组用例（经 /testcases/ids 按分组名圈定整组，非 group_id），页级计数联动', async () => {
    const user = setupUser()
    render(<Harness />)
    await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
    // g1 共 6 条全选，列表头「已选择 6 个用例」
    await waitFor(() => {
      expect(screen.getByText('已选择 6 个用例')).toBeInTheDocument()
    })
    // INT-1267 审计 P1 契约：body 传 group 分组名（后端 filter_by(name=group)），不再传 group_id UUID
    expect(fetchCaseIdsByFilter).toHaveBeenCalledWith(
      expect.objectContaining({ group: '智能音箱功能测试' })
    )
    expect(fetchCaseIdsByFilter).not.toHaveBeenCalledWith(
      expect.objectContaining({ groupId: expect.anything() })
    )
  })

  it('INT-1267 审计 P2：全局算法生效时组内懒加载与组头全选合并算法筛选（index 生效 filters 同源）', async () => {
    const user = setupUser()
    // 模拟 index.tsx effectiveFilters：全局算法已合并进 filters
    render(<Harness filters={{ algorithmType: 'asr-v3' }} />)
    await user.click(screen.getByText('智能音箱功能测试'))
    await screen.findByText('智能音箱-播放音乐')
    // 组内懒加载请求携带当前生效算法筛选（与列表 query 同口径，审计 P2 根因）
    expect(fetchTestCasesByGroup).toHaveBeenCalledWith(
      'g1',
      expect.objectContaining({ algorithmType: 'asr-v3' }),
      expect.any(Number),
      expect.any(Number)
    )
    // 组头全选经 /testcases/ids 圈定整组时 body 携带算法筛选（不再圈定含非当前算法用例）
    await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
    await waitFor(() => {
      expect(fetchCaseIdsByFilter).toHaveBeenCalledWith(
        expect.objectContaining({ group: '智能音箱功能测试', algorithmType: 'asr-v3' })
      )
    })
  })

  it('审计 P3：工具栏「未分组」哨兵筛选（__ungrouped__）时分组视图不再空白，虚拟未分组卡承接', async () => {
    const user = setupUser()
    const ungroupedCases = [
      { ...CASES[0], id: 'tc-u1', name: '未分组-用例1', groupId: null, groupName: null },
      { ...CASES[0], id: 'tc-u2', name: '未分组-用例2', groupId: null, groupName: null },
    ]
    // 哨兵契约：__ungrouped__ 组内懒加载返回 groupId=null 用例（fetchTestCases 不携带 group_id 拉大页后前端过滤）
    const originalImpl = vi.mocked(fetchTestCasesByGroup).getMockImplementation()
    vi.mocked(fetchTestCasesByGroup).mockImplementation(
      async (groupId: string, _filters: unknown, page = 1, perPage = 20) => {
        const matched =
          groupId === '__ungrouped__'
            ? ungroupedCases
            : CASES.filter((c) => (c.groupId ?? '__ungrouped__') === groupId)
        return {
          items: matched.slice((page - 1) * perPage, page * perPage),
          total: matched.length,
        }
      }
    )
    try {
      render(<Harness cases={ungroupedCases} filters={{ groupId: '__ungrouped__' }} />)
      // 真实分组被哨兵筛空（visibleGroups=[]），虚拟未分组组卡承接渲染（原先被 !filters.groupId 守卫抑制）
      expect(screen.getByText('未分组')).toBeInTheDocument()
      expect(screen.getByText('2 条')).toBeInTheDocument()
      // 展开可见未分组用例，组内懒加载按哨兵契约过滤（groupId=null 用例）
      await user.click(screen.getByText('未分组'))
      expect(await screen.findByText('未分组-用例1')).toBeInTheDocument()
      expect(screen.getByText('未分组-用例2')).toBeInTheDocument()
    } finally {
      if (originalImpl) vi.mocked(fetchTestCasesByGroup).mockImplementation(originalImpl)
      else vi.mocked(fetchTestCasesByGroup).mockReset()
    }
  })

  it('审计 P3：收藏视图组头全选降级为已加载用例（不走 /testcases/ids，不圈定含非收藏用例）', async () => {
    const user = setupUser()
    const favoriteCases = [CASES[0], CASES[1]]
    // 收藏态组内懒加载只返回收藏子集（favorite=true 进 fetchTestCases，mock 按组切片）
    const originalImpl = vi.mocked(fetchTestCasesByGroup).getMockImplementation()
    vi.mocked(fetchTestCasesByGroup).mockImplementation(
      async (groupId: string, _filters: unknown, page = 1, perPage = 20) => {
        const matched = favoriteCases.filter((c) => c.groupId === groupId)
        return {
          items: matched.slice((page - 1) * perPage, page * perPage),
          total: matched.length,
        }
      }
    )
    try {
      render(<Harness cases={favoriteCases} filters={{ favorite: true }} />)
      await user.click(screen.getByText('智能音箱功能测试'))
      await screen.findByText('智能音箱-播放音乐')
      // 非收藏用例不在可见集
      expect(screen.queryByText('智能音箱-语音点歌')).not.toBeInTheDocument()
      // 收藏态组头全选：不触发 /testcases/ids（后端 fetch_case_ids 不支持 favorite），
      // 降级为已加载（收藏）用例圈定——不波及不可见非收藏用例
      await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
      expect(fetchCaseIdsByFilter).not.toHaveBeenCalled()
      await waitFor(() => {
        expect(screen.getByText('已选择 2 个用例')).toBeInTheDocument()
      })
    } finally {
      if (originalImpl) vi.mocked(fetchTestCasesByGroup).mockImplementation(originalImpl)
      else vi.mocked(fetchTestCasesByGroup).mockReset()
    }
  })

  it('INT-1267 组内懒加载页续：首屏 20 条，加载更多补齐', async () => {
    const user = setupUser()
    const bigCases = Array.from({ length: 25 }, (_, i) => ({
      ...CASES[0],
      id: `tc-big-${i}`,
      name: `大组-用例-${i}`,
      groupId: 'g1',
      groupName: '智能音箱功能测试',
    }))
    // 本测试全程按组返回大组数据（持久 mock），结束后恢复基准实现
    const originalImpl = vi.mocked(fetchTestCasesByGroup).getMockImplementation()
    vi.mocked(fetchTestCasesByGroup).mockImplementation(
      async (groupId: string, _filters: unknown, page = 1, perPage = 20) => {
        const matched = bigCases.filter((c) => c.groupId === groupId)
        return {
          items: matched.slice((page - 1) * perPage, page * perPage),
          total: matched.length,
        }
      }
    )
    try {
      render(<Harness />)
      // 默认收起 → 先展开 g1 分组卡
      await user.click(screen.getByText('智能音箱功能测试'))
      // 首屏 20 条（perPage=20），第 21 条不可见
      expect(await screen.findByText('大组-用例-19')).toBeInTheDocument()
      expect(screen.queryByText('大组-用例-20')).not.toBeInTheDocument()
      expect(screen.getByText(/已显示 20 \/ 25 条 · 加载更多/)).toBeInTheDocument()
      // 点击加载更多 → 补齐全部 25 条，加载更多行消失
      await user.click(screen.getByText(/加载更多/))
      expect(await screen.findByText('大组-用例-20')).toBeInTheDocument()
      expect(screen.getByText('大组-用例-24')).toBeInTheDocument()
      await waitFor(() => {
        expect(screen.queryByText(/加载更多/)).not.toBeInTheDocument()
      })
    } finally {
      if (originalImpl) vi.mocked(fetchTestCasesByGroup).mockImplementation(originalImpl)
      else vi.mocked(fetchTestCasesByGroup).mockReset()
    }
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
    await screen.findByText('智能音箱-播放音乐')
    // 默认态 = 平铺：用例卡直接渲染，无子分组头
    expect(screen.getByText('智能音箱-播放音乐')).toBeInTheDocument()
    expect(screen.queryByText('未设置标签')).not.toBeInTheDocument()
    // 点击第一个分组卡（g1）组头的「按标签」切换
    const toggles = screen.getAllByText('按标签')
    await user.click(toggles[0])
    // g1 可见用例含 tc-001（音箱）与 5 条无标签 → 标签子组「音箱」（组头 + 卡内 TagBadge 多处出现）
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
    expect(await screen.findByText('该分组下用例均未设置标签')).toBeInTheDocument()
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
      await screen.findByText('智能音箱-播放音乐')
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

  it('INT-1970：列表头「全选用例」传 filtered 回调时按筛选全量圈定（不按已加载用例）', async () => {
    const user = setupUser()
    const onToggleAll = vi.fn()
    const onToggleAllFiltered = vi.fn()
    render(
      <QueryClientProvider client={queryClient}>
        <GroupedCaseList
          groups={GROUPS}
          cases={CASES}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={new Set()}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onBatchAction={vi.fn()}
          onToggleAll={onToggleAll}
          onToggleAllFiltered={onToggleAllFiltered}
          allFilteredSelected={false}
        />
      </QueryClientProvider>
    )
    await user.click(screen.getByLabelText('全选用例'))
    // filtered 口径：交给页级按 POST /testcases/ids 全量圈定，不再把已加载 cases 传下去
    expect(onToggleAllFiltered).toHaveBeenCalledWith(true)
    expect(onToggleAll).not.toHaveBeenCalled()
  })

  it('INT-1970：勾选态取 allFilteredSelected（已选数=筛选总数），不再看已加载页是否全选', () => {
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <GroupedCaseList
          groups={GROUPS}
          cases={CASES}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={new Set(CASES.map((c) => c.id))}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onBatchAction={vi.fn()}
          onToggleAll={vi.fn()}
          onToggleAllFiltered={vi.fn()}
          allFilteredSelected={false}
        />
      </QueryClientProvider>
    )
    // 已加载用例全选但筛选总数更大（真实库 580 vs 已加载 100）→ 不得显示为全选
    expect(screen.getByLabelText('全选用例')).toHaveAttribute('aria-checked', 'false')
    rerender(
      <QueryClientProvider client={queryClient}>
        <GroupedCaseList
          groups={GROUPS}
          cases={CASES}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={new Set(CASES.map((c) => c.id))}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onBatchAction={vi.fn()}
          onToggleAll={vi.fn()}
          onToggleAllFiltered={vi.fn()}
          allFilteredSelected
        />
      </QueryClientProvider>
    )
    expect(screen.getByLabelText('全选用例')).toHaveAttribute('aria-checked', 'true')
  })

  it('INT-1970 返工：allFilteredSelected 生效时全部折叠分组卡组头勾选态同步已勾选', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <GroupedCaseList
          groups={GROUPS}
          cases={CASES}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={new Set(CASES.map((c) => c.id))}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          onBatchAction={vi.fn()}
          onToggleAll={vi.fn()}
          onToggleAllFiltered={vi.fn()}
          allFilteredSelected
        />
      </QueryClientProvider>
    )
    // 表头「全选用例」已生效（已选数=筛选总数）→ 各分组卡（默认折叠、组内 list 未加载）勾选态显示已勾选
    for (const g of GROUPS) {
      expect(screen.getByLabelText(`全选分组 ${g.name}`)).toHaveAttribute('aria-checked', 'true')
    }
    expect(screen.getByLabelText('全选用例')).toHaveAttribute('aria-checked', 'true')
  })

  it('INT-1970 返工：折叠分组组头勾选后勾选态立即翻转（按该组全量判定，不依赖展开加载 list）', async () => {
    const user = setupUser()
    render(<Harness />)
    // 默认折叠点组头勾选 → 经 /testcases/ids 圈定整组 → 组头勾选态翻转（原先折叠时恒未勾选）
    await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
    await waitFor(() => {
      expect(screen.getByLabelText('全选分组 智能音箱功能测试')).toHaveAttribute(
        'aria-checked',
        'true'
      )
    })
    // 再点一次取消 → 组头勾选态同步复位
    await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
    await waitFor(() => {
      expect(screen.getByLabelText('全选分组 智能音箱功能测试')).toHaveAttribute(
        'aria-checked',
        'false'
      )
    })
  })

  it('INT-1970 返工 P2-2：折叠分组组头全选后批量菜单按整组全量下发（不再按已加载页 20 条）', async () => {
    const user = setupUser()
    const onBatchAction = vi.fn()
    render(
      <QueryClientProvider client={queryClient}>
        <GroupedCaseList
          groups={GROUPS}
          cases={CASES}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={new Set()}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          actionCallbacks={actionCallbacks}
          onBatchAction={onBatchAction}
          onToggleAll={vi.fn()}
        />
      </QueryClientProvider>
    )
    // 默认折叠点组头「全选分组」→ 组内全量 ID 缓存（g1 整组 6 条）
    await user.click(screen.getByLabelText('全选分组 智能音箱功能测试'))
    await waitFor(() => {
      expect(fetchCaseIdsByFilter).toHaveBeenCalledWith(
        expect.objectContaining({ group: '智能音箱功能测试' })
      )
    })
    // 折叠态（组内 list 未加载）打开该组批量菜单 → 批量范围 = 整组全量，非已加载页
    await user.click(screen.getByRole('button', { name: '智能音箱功能测试 批量修改' }))
    await user.click(await screen.findByText('评价维度'))
    await waitFor(() => {
      expect(onBatchAction).toHaveBeenCalledWith('dimensions', [
        'tc-001',
        'tc-002',
        'tc-003',
        'tc-004',
        'tc-005',
        'tc-006',
      ])
    })
  })

  it('INT-1970 返工 P2-2：折叠分组未触发组头全选时批量菜单补取整组全量一次', async () => {
    const user = setupUser()
    const onBatchAction = vi.fn()
    render(
      <QueryClientProvider client={queryClient}>
        <GroupedCaseList
          groups={GROUPS}
          cases={CASES}
          loading={false}
          trash={false}
          hasQueryFilters={false}
          filters={{}}
          selected={new Set()}
          tagRegistry={MOCK_TAGS as TagItem[]}
          callbacks={noopCallbacks}
          actionCallbacks={actionCallbacks}
          onBatchAction={onBatchAction}
          onToggleAll={vi.fn()}
        />
      </QueryClientProvider>
    )
    // 折叠态（未展开、未触发组头全选）直接打开批量菜单 → 点菜单项时补取整组 /ids
    await user.click(screen.getByRole('button', { name: '智能音箱功能测试 批量修改' }))
    await user.click(await screen.findByText('噪声'))
    await waitFor(() => {
      expect(onBatchAction).toHaveBeenCalledWith('noise', [
        'tc-001',
        'tc-002',
        'tc-003',
        'tc-004',
        'tc-005',
        'tc-006',
      ])
    })
    // 未触发过组头全选 → 菜单项点击时补取整组 /ids 一次（此后组内全量已缓存）
    expect(fetchCaseIdsByFilter).toHaveBeenCalledWith(
      expect.objectContaining({ group: '智能音箱功能测试' })
    )
    expect(fetchCaseIdsByFilter).toHaveBeenCalledTimes(1)
  })

  /**
   * INT-2154：分组卡计数取自 /groups 全量、不随搜索变化，命中分组若排在分页第一屏外，
   * 用户会以为「搜索没生效」。搜索态须按命中收窄分组集合、组头改显命中数并给汇总。
   */
  it('INT-2154：搜索态只渲染命中分组，组头显示「命中 N 条」并给命中汇总', async () => {
    const hitCases = CASES.filter((c) => c.name.includes('闹钟'))
    render(<Harness cases={hitCases} filters={{ search: '闹钟' }} />)

    // 等命中聚合到位（组头从「6 条」切成「命中 2 条」）后再断言分组集合收窄
    expect(await screen.findByText('命中 2 条')).toBeInTheDocument()
    expect(screen.getByText('智能音箱功能测试')).toBeInTheDocument()
    expect(screen.queryByText('车载语音交互')).not.toBeInTheDocument()
    expect(screen.queryByText('待归档分组')).not.toBeInTheDocument()
    // 组头保留分组全量作对照
    expect(screen.getByText('共 6 条')).toBeInTheDocument()
    // 汇总行：命中总量 + 命中分组数（数字节点被 <span> 包裹，按 status 容器整体取文本）
    expect(screen.getByRole('status').textContent).toContain(
      '命中 2 条用例，分布在 1 个分组'
    )
  })

  it('INT-2154：搜索无命中时空态说明是搜索没命中（不再只说清空分组/标签）', () => {
    render(<Harness cases={[]} filters={{ search: 'zzz_no_such_case' }} />)

    expect(screen.getByText('没有找到符合条件的测试用例')).toBeInTheDocument()
    expect(
      screen.getByText('当前搜索没有命中用例，可清空搜索词或切换到「按标签」视图')
    ).toBeInTheDocument()
  })
})
