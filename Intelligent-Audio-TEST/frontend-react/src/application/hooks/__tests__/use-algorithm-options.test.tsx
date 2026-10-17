/**
 * 全局算法选项 hook 单测（接线壳 INT-607，代码审计 P2 回归）：
 * queryKey 用独立前缀 ['shell','algorithm','options']，与评估域「关联算法」
 * facet 的 ['algorithm','options']（evaluation-api mock → {value,label}）隔离——
 * 同 key 共享缓存会让先填充的一方决定 data 形态、另一方字段读空白。
 * 无 algorithm:read（device_admin/guest）不发请求（enabled: canRead）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { useAlgorithmOptions as useEvaluationAlgorithmOptions } from '@/application/evaluation/use-dimensions'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import type { AuthUser } from '@/domain/models/user'
import type { AlgorithmSwitchOption } from '@/domain/models/algorithm'

const fetchMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/algorithm-api', () => ({
  fetchAlgorithmOptions: fetchMock,
}))

const REAL_OPTIONS: AlgorithmSwitchOption[] = [
  { value: 'voice_llm', name: '语音大模型' },
  { value: 'audio_sep', name: '音频分离' },
]

function makeUser(username: string, permissions: string[]): AuthUser {
  return {
    id: '1',
    username,
    displayName: username,
    roleName: username,
    permissions,
  }
}

function renderWithClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

describe('useAlgorithmOptions queryKey 隔离（代码审计 P2 回归）', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(REAL_OPTIONS)
    useAuthStore.setState({ user: null })
  })

  it("queryKey 为 ['shell','algorithm','options']，与评估域 ['algorithm','options'] 不共享", async () => {
    useAuthStore.setState({
      user: makeUser('tester', ['algorithm:read']),
    })
    const { client, wrapper } = renderWithClient()

    renderHook(() => useAlgorithmOptions(), { wrapper })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const keys = client
      .getQueryCache()
      .findAll()
      .map((query) => query.queryKey)
    expect(keys).toContainEqual(['shell', 'algorithm', 'options'])
    expect(keys).not.toContainEqual(['algorithm', 'options'])
  })

  it('返回 {value,name} 真实契约（AlgorithmSwitchOption，非评估域 {value,label}）', async () => {
    useAuthStore.setState({
      user: makeUser('tester', ['algorithm:read']),
    })
    const { wrapper } = renderWithClient()

    const { result } = renderHook(() => useAlgorithmOptions(), { wrapper })
    await waitFor(() => expect(result.current.options).toEqual(REAL_OPTIONS))
    expect(result.current.options[0]).toHaveProperty('name')
    expect(result.current.options[0]).not.toHaveProperty('label')
  })

  it('无 algorithm:read（device_admin/guest）→ 不发请求、返回空列表', async () => {
    useAuthStore.setState({
      user: makeUser('device_admin', ['device:read']),
    })
    const { wrapper } = renderWithClient()

    const { result } = renderHook(() => useAlgorithmOptions(), { wrapper })
    expect(result.current.options).toEqual([])
    expect(result.current.canRead).toBe(false)
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('与评估域「关联算法」hook 同挂载不串数据：各持各契约（壳 {value,name} / 评估 {value,label}）', async () => {
    useAuthStore.setState({
      user: makeUser('tester', ['algorithm:read']),
    })
    const { wrapper } = renderWithClient()

    const shell = renderHook(() => useAlgorithmOptions(), { wrapper })
    const evaluation = renderHook(() => useEvaluationAlgorithmOptions(), {
      wrapper,
    })

    // 两 hook 各自 queryFn 都触发（评估域 mock 120ms 延迟）
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(evaluation.result.current.data).toBeDefined())
    await waitFor(() => expect(shell.result.current.options).toHaveLength(2))

    // 壳 hook 读 {value,name}：切换器下拉 name 有值
    expect(shell.result.current.options[0]?.name).toBe('语音大模型')
    // 评估域 hook 读 {value,label}：facet 下拉 label 有值（非 undefined 空白）
    const evaluationOptions = evaluation.result.current.data ?? []
    expect(evaluationOptions[0]?.label).toBe('通用识别引擎')
    expect(evaluationOptions[0]).not.toHaveProperty('name')
  })
})
