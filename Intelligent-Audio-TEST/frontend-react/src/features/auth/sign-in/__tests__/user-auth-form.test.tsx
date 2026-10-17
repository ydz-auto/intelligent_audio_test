/**
 * 登录表单组件测试（INT-606 认证接线）：字段校验内联 / 真实登录成功回写
 * token+store / 105 加密失败卡内 Alert / 106 凭证错误 sonner toast /
 * 网络失败 toast / 加密初始化失败 Alert（对位 12_登录与错误页.md §3.4 三层分离）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UserAuthForm } from '@/features/auth/sign-in/components/user-auth-form'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { authTokenStore } from '@/infrastructure/storage/auth-token'
import { ApiError } from '@/infrastructure/api/api-error'
import { PasswordEncryptionUnavailableError } from '@/infrastructure/api/password-encryption'
import { AUTH_ERROR_COPY, AuthErrorCode } from '@/domain/models/auth'
import { ApiErrorCode } from '@/domain/models/api'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const { loginMock, listProvidersMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  listProvidersMock: vi.fn(),
}))

vi.mock('@/infrastructure/api/authApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/authApi')>()
  return {
    ...actual,
    authApi: {
      ...actual.authApi,
      login: loginMock,
      listPublicOAuthProviders: listProvidersMock,
    },
  }
})

const initialAuth = useAuthStore.getState()

beforeEach(() => {
  vi.spyOn(toast, 'success')
  vi.spyOn(toast, 'error')
  listProvidersMock.mockResolvedValue([
    { id: '1', name: 'GitHub', slug: 'github', icon: 'github' },
    { id: '2', name: '企业统一认证', slug: 'oidc', icon: 'oidc' },
  ])
})

afterEach(() => {
  useAuthStore.setState(initialAuth)
  authTokenStore.clear()
  vi.restoreAllMocks()
  navigateMock.mockReset()
  loginMock.mockReset()
})

function renderForm(redirectTo?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  render(
    <QueryClientProvider client={client}>
      <UserAuthForm redirectTo={redirectTo} />
    </QueryClientProvider>
  )
}

async function fillAndSubmit(username: string, password: string) {
  const user = userEvent.setup()
  renderForm()
  await user.type(screen.getByLabelText('用户名或电子邮件'), username)
  await user.type(screen.getByLabelText('密码'), password)
  await user.click(screen.getByRole('button', { name: '登 录' }))
  return user
}

function apiError(
  code: ApiErrorCode | null,
  httpStatus: number | null,
  opts: { message?: string; detail?: string; isNetworkError?: boolean } = {}
): ApiError {
  return new ApiError({
    code,
    httpStatus,
    message: opts.message ?? '',
    detail: opts.detail,
    isNetworkError: opts.isNetworkError,
  })
}

describe('UserAuthForm（认证接线真实登录）', () => {
  it('空表单提交显示字段校验错误（不发起登录）', async () => {
    const user = userEvent.setup()
    renderForm()
    await user.click(screen.getByRole('button', { name: '登 录' }))
    expect(await screen.findByText('请输入用户名或邮箱')).toBeInTheDocument()
    expect(await screen.findByText('请输入密码')).toBeInTheDocument()
    expect(loginMock).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('真实登录成功：authApi.login 回包 → token/user 落库、toast 欢迎并跳转工作台', async () => {
    loginMock.mockResolvedValue({
      accessToken: 'access-1',
      user: {
        id: '1',
        username: 'admin',
        displayName: '管理员',
        roleName: '超级管理员',
        permissions: ['*'],
      },
    })
    await fillAndSubmit('admin', 'secret')
    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('欢迎回来！')
    )
    expect(loginMock).toHaveBeenCalledWith({ username: 'admin', password: 'secret' })
    expect(authTokenStore.get()).toBe('access-1')
    expect(useAuthStore.getState().user?.username).toBe('admin')
    expect(navigateMock).toHaveBeenCalledWith({ to: '/dashboard' })
  })

  it('redirect 参数存在时成功回跳 sanitize 后的目标', async () => {
    loginMock.mockResolvedValue({
      accessToken: 'access-2',
      user: {
        id: '1',
        username: 'admin',
        displayName: '管理员',
        roleName: '超级管理员',
        permissions: ['*'],
      },
    })
    const user = userEvent.setup()
    renderForm('/tasks')
    await user.type(screen.getByLabelText('用户名或电子邮件'), 'admin')
    await user.type(screen.getByLabelText('密码'), 'secret')
    await user.click(screen.getByRole('button', { name: '登 录' }))
    await vi.waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({ to: '/tasks' })
    )
  })

  it('错误码 105：卡内 Alert 呈现加密校验失败（不走 toast、不跳转）', async () => {
    loginMock.mockRejectedValue(
      apiError(ApiErrorCode.AUTH_ENCRYPTION_INVALID, 401, {
        message: '登录加密校验失败，请刷新页面重试',
      })
    )
    await fillAndSubmit('admin', 'secret')
    expect(
      await screen.findByText(AUTH_ERROR_COPY[AuthErrorCode.ENCRYPTION_INVALID])
    ).toBeInTheDocument()
    expect(toast.error).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('错误码 106：sonner toast 呈现凭证错误，登录态保持为空', async () => {
    loginMock.mockRejectedValue(
      apiError(ApiErrorCode.AUTH_CREDENTIALS_INVALID, 401, {
        message: '用户名或密码错误',
      })
    )
    await fillAndSubmit('admin', 'wrong')
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        AUTH_ERROR_COPY[AuthErrorCode.CREDENTIALS_INVALID]
      )
    )
    expect(useAuthStore.getState().user).toBeNull()
    expect(authTokenStore.get()).toBeNull()
  })

  it('网络失败：sonner toast 呈现网络异常文案', async () => {
    loginMock.mockRejectedValue(
      apiError(null, null, { isNetworkError: true, detail: 'Failed to fetch' })
    )
    await fillAndSubmit('admin', 'secret')
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        '网络异常，请检查连接后重试'
      )
    )
  })

  it('加密初始化失败（前端拿不到公钥）：卡内 Alert 引导刷新', async () => {
    loginMock.mockRejectedValue(new PasswordEncryptionUnavailableError())
    await fillAndSubmit('admin', 'secret')
    expect(
      await screen.findByText('登录加密初始化失败，请刷新页面重试')
    ).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('其他服务端错误：toast 呈现「登录失败：{detail}」', async () => {
    loginMock.mockRejectedValue(
      apiError(null, 500, { message: '服务内部异常' })
    )
    await fillAndSubmit('admin', 'secret')
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('登录失败：服务内部异常')
    )
  })

  it('OAuth 提供方按真实列表动态渲染（分隔线 + 按钮逐项）', async () => {
    renderForm()
    expect(await screen.findByText('或使用账号登录')).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: '使用 GitHub 登录' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '使用 企业统一认证 登录' })
    ).toBeInTheDocument()
  })

  it('OAuth 提供方为空：整区不渲染（含分隔线）', async () => {
    listProvidersMock.mockResolvedValue([])
    renderForm()
    await vi.waitFor(() => expect(listProvidersMock).toHaveBeenCalled())
    expect(screen.queryByText('或使用账号登录')).not.toBeInTheDocument()
  })
})
