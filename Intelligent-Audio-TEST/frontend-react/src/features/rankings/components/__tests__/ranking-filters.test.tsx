/**
 * 排行榜筛选行组件测试（INT-514 返修，审计 P2-1/P2-2 对应回归）：
 * - P2-1：重置清空主体搜索——本地输入同步清空，防抖 effect 不回灌旧值；
 *   外部把 subjectName 清空（URL 回退）同样同步清空输入。
 * - P2-2：筛选行「立即计算」只触发页面层统一 onCompute（确认弹窗由页面层持有，
 *   空态/筛选行共用同一重算链路——§5.2）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RankingFilters } from '@/domain/models/benchmark'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

import { RankingFiltersBar } from '../ranking-filters'

// INT-1619：指标下拉的真实数据源来自 /benchmarks/metric-mappings（jsdom 里不发请求）。
// 闭合态触发器必须显示 metricName 而不是 metricCode。
vi.mock('@/application/rankings/useMetricMappings', () => ({
  useMetricMappings: () => ({
    mappings: [
      {
        id: 1,
        dimensionName: '环境',
        metricCode: 'ENV_UNDERSTAND_SCORE',
        metricName: '环境理解评分',
        unit: '分',
        direction: 'higher_is_better',
        scenarioTags: [],
        active: true,
      },
    ],
    isLoading: false,
    isFailed: false,
  }),
}))

const initialAuth = useAuthStore.getState()

/** AUTH_MODE=off 开放模式启动引导回填的 dev_user（后端 AuthMiddleware off 分支：permissions=['*']） */
const devUser = {
  id: '0',
  username: 'dev_user',
  displayName: 'dev_user',
  roleName: '',
  permissions: ['*'],
}

const DEFAULT_FILTERS: RankingFilters = {
  category: '',
  suite: '',
  metricCode: '',
  source: '',
  subjectName: '',
}

beforeEach(() => {
  // AUTH_MODE=off 开放模式：启动引导（ensureAuthSession→hydrateSession）回填
  // dev_user（permissions=['*']）通配放行——与页面走查同口径。INT-1225 起
  // user=null 匿名不再放行计算权限（改走 403/只读降级态），故不能再用 setAuth(null)。
  useAuthStore.getState().setAuth(devUser)
})

afterEach(() => {
  useAuthStore.setState(initialAuth)
})

function renderBar(
  props: Partial<{
    filters: RankingFilters
    suites: string[]
    isFetching: boolean
    computePending: boolean
  }>
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const onFilterChange = vi.fn()
  const onReset = vi.fn()
  const onCompute = vi.fn()
  const utils = render(
    <QueryClientProvider client={client}>
      <RankingFiltersBar
        filters={props.filters ?? DEFAULT_FILTERS}
        suites={props.suites ?? ['general']}
        onFilterChange={onFilterChange}
        onReset={onReset}
        isFetching={props.isFetching ?? false}
        onCompute={onCompute}
        computePending={props.computePending ?? false}
      />
    </QueryClientProvider>
  )
  return { ...utils, onFilterChange, onReset, onCompute }
}

describe('RankingFiltersBar 主体搜索重置（P2-1）', () => {
  it('点「重置」：本地输入同步清空，且防抖不再把旧值回灌 onFilterChange', async () => {
    const user = userEvent.setup()
    const { onReset, onFilterChange } = renderBar({
      filters: { ...DEFAULT_FILTERS, suite: 'general', subjectName: '远场' },
    })

    const input = screen.getByRole('textbox', { name: '搜索主体' })
    expect(input).toHaveValue('远场')

    await user.click(screen.getByRole('button', { name: '重置' }))
    expect(onReset).toHaveBeenCalledTimes(1)
    // 重置后输入框立即清空
    await waitFor(() => expect(input).toHaveValue(''))
    // 跨过 300ms 防抖窗口：不得回灌 subjectName=远场（URL 复活路径）
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(onFilterChange).not.toHaveBeenCalledWith({ subjectName: '远场' })
  })

  it('外部把 subjectName 清空（URL 回退/重置导航）时输入框同步清空且不回灌', async () => {
    const { onFilterChange, rerender } = renderBar({
      filters: { ...DEFAULT_FILTERS, suite: 'general', subjectName: '远场' },
    })

    const input = screen.getByRole('textbox', { name: '搜索主体' })
    expect(input).toHaveValue('远场')

    // 模拟外部导航（重置/URL 回退）已把 filters.subjectName 变为空串
    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}
      >
        <RankingFiltersBar
          filters={{ ...DEFAULT_FILTERS, suite: 'general' }}
          suites={['general']}
          onFilterChange={onFilterChange}
          onReset={vi.fn()}
          isFetching={false}
          onCompute={vi.fn()}
          computePending={false}
        />
      </QueryClientProvider>
    )
    await waitFor(() => expect(input).toHaveValue(''))
    // 跨过防抖窗口：不回灌旧值
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(onFilterChange).not.toHaveBeenCalledWith({ subjectName: '远场' })
  })
})

describe('RankingFiltersBar 筛选 Select 闭合态文案（INT-1619）', () => {
  it('指标 / 数据来源有选中值时，触发器显示中文标签而不是原始枚举', () => {
    renderBar({
      filters: {
        ...DEFAULT_FILTERS,
        metricCode: 'ENV_UNDERSTAND_SCORE',
        source: 'platform_test',
      },
    })

    const metricTrigger = screen.getByLabelText('指标')
    expect(metricTrigger).toHaveTextContent('环境理解评分')
    expect(metricTrigger).not.toHaveTextContent('ENV_UNDERSTAND_SCORE')

    const sourceTrigger = screen.getByLabelText('数据来源')
    expect(sourceTrigger).toHaveTextContent('平台实测')
    expect(sourceTrigger).not.toHaveTextContent('platform_test')
  })

  it('未选中时触发器显示 placeholder 全部指标 / 全部来源', () => {
    renderBar({})

    expect(screen.getByLabelText('指标')).toHaveTextContent('全部指标')
    expect(screen.getByLabelText('数据来源')).toHaveTextContent('全部来源')
  })
})

describe('RankingFiltersBar 立即计算（P2-2 上提）', () => {
  it('有 compute 权限：按钮触发页面层 onCompute（确认弹窗由页面层统一持有）', async () => {
    const user = userEvent.setup()
    const { onCompute } = renderBar({})
    await user.click(screen.getByRole('button', { name: '立即计算' }))
    expect(onCompute).toHaveBeenCalledTimes(1)
  })

  it('computePending 时按钮显示「计算中…」', async () => {
    renderBar({ computePending: true })
    expect(screen.getByText('计算中…')).toBeInTheDocument()
  })

  it('无计算权限（user=null 匿名）：「立即计算」不渲染（INT-1225 降级口径）', () => {
    useAuthStore.getState().setAuth(null)
    renderBar({})
    expect(
      screen.queryByRole('button', { name: '立即计算' })
    ).not.toBeInTheDocument()
    expect(screen.queryByText('计算中…')).not.toBeInTheDocument()
  })
})
