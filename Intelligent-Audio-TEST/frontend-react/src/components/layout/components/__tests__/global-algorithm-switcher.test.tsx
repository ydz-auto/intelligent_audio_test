/**
 * 全局算法切换器测试（接线·壳 INT-607，02_导航栏.md §3.4）：
 * 无 algorithm:read 整钮隐藏（隐藏而非置灰）；真实 options 渲染替换 mock；
 * 持久化值不在 options（算法下线/删除）→ 静默回落「全部算法」；选中写回全局 store。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithmApi'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { GlobalAlgorithmSwitcher } from '@/components/layout/components/global-algorithm-switcher'

vi.mock('@/infrastructure/api/authApi', () => ({
  authApi: {
    login: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
    getAuthMode: vi.fn(),
  },
}))

vi.mock('@/infrastructure/api/algorithmApi', () => ({
  fetchAlgorithmOptions: vi.fn(),
}))

function makeUser(permissions: string[]) {
  return {
    id: '1',
    username: 'u',
    displayName: 'u',
    roleName: '',
    permissions,
  }
}

const REAL_OPTIONS = [
  { id: 'asr-v3', name: '通用识别引擎', version: '', description: '', enabled: true },
  { id: 'asr-stream', name: '流式识别引擎', version: '', description: '', enabled: true },
]

function renderSwitcher() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<GlobalAlgorithmSwitcher />, { wrapper })
}

const triggerName = '切换全局算法'

describe('GlobalAlgorithmSwitcher', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    useAlgorithmStore.setState({ algorithmId: '' })
    vi.clearAllMocks()
  })

  it('无 algorithm:read（device_admin/guest）：整钮隐藏', () => {
    useAuthStore.setState({ user: makeUser(['report:read']) })
    renderSwitcher()
    expect(screen.queryByRole('button', { name: triggerName })).not.toBeInTheDocument()
  })

  it('有 algorithm:read：渲染真实 options 数据（替代 mock 常量）', async () => {
    useAuthStore.setState({ user: makeUser(['algorithm:read']) })
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue(REAL_OPTIONS)
    // 持久化值命中真实 options → 触发钮显示算法名
    useAlgorithmStore.setState({ algorithmId: 'asr-v3' })
    renderSwitcher()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: triggerName })).toHaveTextContent('通用识别引擎')
    })
  })

  it('持久化值不在当前 options → 静默回落「全部算法」', async () => {
    useAuthStore.setState({ user: makeUser(['algorithm:read']) })
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue(REAL_OPTIONS)
    // 持久化值为已下线算法
    useAlgorithmStore.setState({ algorithmId: 'asr-offline-old' })
    renderSwitcher()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: triggerName })).toHaveTextContent('全部算法')
    })
  })

  it('打开面板选中算法 → 写回全局 store（跨组件同步点）', async () => {
    const user = userEvent.setup()
    useAuthStore.setState({ user: makeUser(['algorithm:read']) })
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue(REAL_OPTIONS)
    useAlgorithmStore.setState({ algorithmId: '' })
    renderSwitcher()

    await user.click(await screen.findByRole('button', { name: triggerName }))

    await user.click(await screen.findByRole('button', { name: /通用识别引擎/ }))
    await waitFor(() => {
      expect(useAlgorithmStore.getState().algorithmId).toBe('asr-v3')
    })
  })

  it('打开面板选「全部算法」→ 清空 store（algorithmId 空串）', async () => {
    const user = userEvent.setup()
    useAuthStore.setState({ user: makeUser(['algorithm:read']) })
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue(REAL_OPTIONS)
    useAlgorithmStore.setState({ algorithmId: 'asr-v3' })
    renderSwitcher()

    await user.click(await screen.findByRole('button', { name: triggerName }))

    await user.click(await screen.findByRole('button', { name: /全部算法/ }))
    await waitFor(() => {
      expect(useAlgorithmStore.getState().algorithmId).toBe('')
    })
  })
})
