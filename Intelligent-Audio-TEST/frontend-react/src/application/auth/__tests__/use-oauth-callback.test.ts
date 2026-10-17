/**
 * useOAuthCallback 单测（认证接线 INT-606，12_登录与错误页.md §3.5）：
 * oauth_token 成功 loginWithToken + sanitize 回跳 + toast「登录成功」+ URL 清参；
 * oauth_token 失败停留登录页提示重试；oauth_error toast 呈现错误并清参。
 */
import { renderHook, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useOAuthCallback } from '@/application/auth/use-oauth-callback'

const { navigateMock, loginWithTokenMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  loginWithTokenMock: vi.fn(),
}))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('@/infrastructure/stores/auth-store', () => ({
  useAuthStore: { getState: () => ({ loginWithToken: loginWithTokenMock }) },
}))

function renderCallback(params: {
  oauthToken?: string
  oauthError?: string
  redirectTo?: string
}) {
  return renderHook(() => useOAuthCallback(params))
}

beforeEach(() => {
  vi.spyOn(toast, 'success')
  vi.spyOn(toast, 'error')
})

afterEach(() => {
  vi.restoreAllMocks()
  navigateMock.mockReset()
  loginWithTokenMock.mockReset()
})

describe('useOAuthCallback', () => {
  it('无 OAuth 参数：不登录不跳转，非处理态', () => {
    const { result } = renderCallback({})
    expect(result.current.processing).toBe(false)
    expect(loginWithTokenMock).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('oauth_token 成功：loginWithToken + toast「登录成功」+ 回跳工作台 + 清参', async () => {
    loginWithTokenMock.mockResolvedValue(undefined)
    const { result } = renderCallback({ oauthToken: 'oauth-t1' })
    await waitFor(() =>
      expect(loginWithTokenMock).toHaveBeenCalledWith('oauth-t1')
    )
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('登录成功')
    )
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({ to: '/dashboard', replace: true })
    )
    expect(result.current.processing).toBe(true)
  })

  it('oauth_token + redirect：回跳 sanitize 后的目标', async () => {
    loginWithTokenMock.mockResolvedValue(undefined)
    renderCallback({ oauthToken: 'oauth-t2', redirectTo: '/tasks' })
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({ to: '/tasks', replace: true })
    )
  })

  it('oauth_token 失败：toast 提示重试并停留登录页（处理态解除）', async () => {
    loginWithTokenMock.mockRejectedValue(new Error('invalid token'))
    const { result } = renderCallback({ oauthToken: 'bad-token' })
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('OAuth 登录失败，请重试')
    )
    await waitFor(() => expect(result.current.processing).toBe(false))
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('oauth_error：toast 呈现错误并清 URL 参数', async () => {
    renderCallback({ oauthError: 'provider_denied' })
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('OAuth 登录失败：provider_denied')
    )
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({
        to: '/login',
        search: {},
        replace: true,
      })
    )
    expect(loginWithTokenMock).not.toHaveBeenCalled()
  })
})
