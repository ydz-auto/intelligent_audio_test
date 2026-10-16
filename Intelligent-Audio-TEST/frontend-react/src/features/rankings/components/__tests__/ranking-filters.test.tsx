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

const initialAuth = useAuthStore.getState()

const DEFAULT_FILTERS: RankingFilters = {
  category: '',
  suite: '',
  metricCode: '',
  source: '',
  subjectName: '',
}

beforeEach(() => {
  // AUTH_MODE=off 默认态（user=null → canCompute=true），与页面走查同口径
  useAuthStore.getState().setAuth(null)
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
})
