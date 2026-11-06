/**
 * useSystemOptions 权限门禁单测（INT-1585）：
 * GET /api/option/ 需要 option:read。匿名（INT-1225：公开页站头不 401）与
 * 已登录但无 option:read 的低权限角色（guest 等，真实复现每页 2 条 403 SEVERE）
 * 都不发请求；持 option:read 或 '*' 通配才拉取。门禁只翻转 enabled，
 * queryKey 恒定——登录/登出/权限刷新不分裂缓存。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSystemOptions } from '@/application/settings/use-system-options'
import type { SystemOptions } from '@/domain/models/option'
import type { AuthUser } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

const fetchMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/optionApi', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/infrastructure/api/optionApi')>()
  return { ...actual, getSystemOptions: fetchMock }
})

const REAL_OPTIONS: SystemOptions = {
  'site.name': '智能语音测试平台',
  'site.notice': '接线测试公告',
}

/** guest 真实权限集（10 条，无 option:read） */
const GUEST_PERMISSIONS = [
  'dashboard:read',
  'task:read',
  'report:read',
  'testcase:read',
  'audio:read',
  'device:read',
  'algorithm:read',
  'sse:read',
  'profile:read',
  'about:read',
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

/** 等一拍，确认禁用态没有迟到的请求发出 */
const flush = () => new Promise((resolve) => setTimeout(resolve, 50))

describe('useSystemOptions 权限门禁（INT-1585）', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(REAL_OPTIONS)
    useAuthStore.setState({ user: null })
  })

  it('匿名（user=null）→ 不发请求，data 为 undefined 且不落 error', async () => {
    const { wrapper } = renderWithClient()

    const { result } = renderHook(() => useSystemOptions(), { wrapper })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isError).toBe(false)
    expect(result.current.data).toBeUndefined()

    await flush()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('已登录但无 option:read（guest 权限集）→ 不发请求，消费方落默认值', async () => {
    useAuthStore.setState({ user: makeUser('接线测试_guest', GUEST_PERMISSIONS) })
    const { wrapper } = renderWithClient()

    const { result } = renderHook(() => useSystemOptions(), { wrapper })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isError).toBe(false)
    expect(result.current.data).toBeUndefined()

    await flush()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('持 option:read → 发 1 次请求并返回 KV', async () => {
    useAuthStore.setState({
      user: makeUser('admin', ['option:read', 'option:write']),
    })
    const { wrapper } = renderWithClient()

    const { result } = renderHook(() => useSystemOptions(), { wrapper })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(result.current.data).toEqual(REAL_OPTIONS))
    expect(result.current.isError).toBe(false)
  })

  it("'*' 通配用户 → 发请求", async () => {
    useAuthStore.setState({ user: makeUser('root', ['*']) })
    const { wrapper } = renderWithClient()

    renderHook(() => useSystemOptions(), { wrapper })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })

  it('权限翻转只改 enabled，queryKey 恒定（缓存不分裂）', async () => {
    useAuthStore.setState({ user: makeUser('admin', ['option:read']) })
    const { client, wrapper } = renderWithClient()

    renderHook(() => useSystemOptions(), { wrapper })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    // 降为无 option:read（如会话重置/权限刷新）→ 不新增请求
    useAuthStore.setState({ user: makeUser('接线测试_guest', GUEST_PERMISSIONS) })
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const keys = client.getQueryCache().findAll().map((query) => query.queryKey)
    expect(keys).toEqual([['system-options']])
  })
})
