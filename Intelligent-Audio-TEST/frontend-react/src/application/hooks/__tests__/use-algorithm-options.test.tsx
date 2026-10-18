/**
 * 全局算法选项 hook 测试（接线·壳 INT-607，02_导航栏.md §3.4）：
 * GET /algorithm/options（algorithm:read 门槛）——无码查询禁用且 isReadonly
 * （切换器整钮隐藏）；有码拉取真实选项映射到 Domain AlgorithmOption。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithmApi'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'

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

function renderOptionsHook() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return renderHook(() => useAlgorithmOptions(), { wrapper })
}

describe('useAlgorithmOptions', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null })
    vi.clearAllMocks()
  })

  it('无 algorithm:read：查询禁用、isReadonly=true（切换器隐藏）', () => {
    useAuthStore.setState({ user: makeUser(['report:read']) })
    const { result } = renderOptionsHook()
    expect(result.current.isReadonly).toBe(true)
    expect(result.current.options).toEqual([])
    expect(fetchAlgorithmOptions).not.toHaveBeenCalled()
  })

  it('有 algorithm:read：拉取真实 options 映射到 Domain AlgorithmOption', async () => {
    useAuthStore.setState({ user: makeUser(['algorithm:read']) })
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue([
      { id: 'asr-v3', name: '通用识别引擎', version: '', description: '', enabled: true },
      { id: 'asr-stream', name: '流式识别引擎', version: '', description: '', enabled: true },
    ])
    const { result } = renderOptionsHook()
    await waitFor(() => expect(result.current.options.length).toBe(2))
    expect(fetchAlgorithmOptions).toHaveBeenCalledTimes(1)
    expect(result.current.options[0]).toMatchObject({ id: 'asr-v3', name: '通用识别引擎' })
    expect(result.current.isReadonly).toBe(false)
  })

  it('超级通配 *：视同有码查询', async () => {
    useAuthStore.setState({ user: makeUser(['*']) })
    vi.mocked(fetchAlgorithmOptions).mockResolvedValue([])
    const { result } = renderOptionsHook()
    await waitFor(() => expect(fetchAlgorithmOptions).toHaveBeenCalledTimes(1))
    expect(result.current.isReadonly).toBe(false)
  })
})
