/**
 * 登录表单组件测试（INT-379 门户）：字段校验内联 / mock 登录成功回写 store /
 * 105 加密失败卡内 Alert / 106 凭证错误 sonner toast（对位 12_登录与错误页.md §3.4 三层分离）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UserAuthForm } from '@/features/auth/sign-in/components/user-auth-form'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { AUTH_ERROR_COPY, AuthErrorCode } from '@/domain/models/auth'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const initialAuth = useAuthStore.getState()

beforeEach(() => {
  vi.spyOn(toast, 'success')
  vi.spyOn(toast, 'error')
})

afterEach(() => {
  useAuthStore.setState(initialAuth)
  vi.restoreAllMocks()
  navigateMock.mockReset()
})

async function fillAndSubmit(username: string, password: string) {
  const user = userEvent.setup()
  render(<UserAuthForm />)
  await user.type(screen.getByLabelText('用户名或电子邮件'), username)
  await user.type(screen.getByLabelText('密码'), password)
  await user.click(screen.getByRole('button', { name: '登 录' }))
  return user
}

describe('UserAuthForm', () => {
  it('空表单提交显示字段校验错误（不发起登录）', async () => {
    const user = userEvent.setup()
    render(<UserAuthForm />)
    await user.click(screen.getByRole('button', { name: '登 录' }))
    expect(await screen.findByText('请输入用户名或邮箱')).toBeInTheDocument()
    expect(await screen.findByText('请输入密码')).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('合法账号登录成功：回写 auth store、toast 欢迎并跳转工作台', async () => {
    await fillAndSubmit('demo_user', 'secret')
    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('欢迎回来！')
    )
    expect(useAuthStore.getState().user?.username).toBe('demo_user')
    expect(navigateMock).toHaveBeenCalledWith({ to: '/dashboard' })
  })

  it('error_105 触发词：卡内 Alert 呈现加密校验失败（不走 toast）', async () => {
    await fillAndSubmit('error_105', 'secret')
    expect(
      await screen.findByText(AUTH_ERROR_COPY[AuthErrorCode.ENCRYPTION_INVALID])
    ).toBeInTheDocument()
    expect(toast.error).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('error_106 触发词：sonner toast 呈现凭证错误', async () => {
    await fillAndSubmit('error_106', 'secret')
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        AUTH_ERROR_COPY[AuthErrorCode.CREDENTIALS_INVALID]
      )
    )
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('OAuth 提供方与演示提示渲染', () => {
    render(<UserAuthForm />)
    expect(screen.getByText('或使用账号登录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '使用 GitHub 登录' })).toBeInTheDocument()
    expect(screen.getByText('演示触发词：error_105 / error_106 / closed')).toBeInTheDocument()
  })
})
