/**
 * 注册表单组件测试（INT-606 认证接线）：字段校验内联 / 真实注册成功引导登录 /
 * 403（注册开关关闭）切引导态 / 400、409 detail 文案 toast
 * （对位 12_登录与错误页.md §3.6）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UserRegisterForm } from '@/features/auth/sign-up/components/user-register-form'
import { ApiError } from '@/infrastructure/api/api-error'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const { registerMock } = vi.hoisted(() => ({ registerMock: vi.fn() }))

vi.mock('@/infrastructure/api/authApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/authApi')>()
  return {
    ...actual,
    authApi: { ...actual.authApi, register: registerMock },
  }
})

beforeEach(() => {
  vi.spyOn(toast, 'success')
  vi.spyOn(toast, 'error')
})

afterEach(() => {
  vi.restoreAllMocks()
  navigateMock.mockReset()
  registerMock.mockReset()
})

async function fillAndSubmit(overrides: Partial<Record<string, string>> = {}) {
  const values = {
    username: 'new_user',
    email: 'new@example.com',
    password: 'secret1',
    confirm: 'secret1',
    ...overrides,
  }
  const user = userEvent.setup()
  render(<UserRegisterForm />)
  await user.type(screen.getByLabelText('用户名'), values.username)
  await user.type(screen.getByLabelText('邮箱'), values.email)
  await user.type(screen.getByLabelText('密码'), values.password)
  await user.type(screen.getByLabelText('确认密码'), values.confirm)
  await user.click(screen.getByRole('button', { name: '注 册' }))
  return user
}

function apiError(
  code: number | null,
  httpStatus: number,
  message = '',
  detail?: string
): ApiError {
  return new ApiError({ code, httpStatus, message, detail })
}

describe('UserRegisterForm（认证接线真实注册）', () => {
  it('空表单提交显示字段校验错误（不发起注册）', async () => {
    const user = userEvent.setup()
    render(<UserRegisterForm />)
    await user.click(screen.getByRole('button', { name: '注 册' }))
    expect(await screen.findByText('请输入用户名')).toBeInTheDocument()
    expect(await screen.findByText('请输入邮箱')).toBeInTheDocument()
    expect(await screen.findByText('请输入密码（至少 6 位）')).toBeInTheDocument()
    expect(await screen.findByText('请再次输入密码')).toBeInTheDocument()
    expect(registerMock).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('两次输入的密码不一致：字段级 refine 错误', async () => {
    const user = userEvent.setup()
    render(<UserRegisterForm />)
    await user.type(screen.getByLabelText('用户名'), 'new_user')
    await user.type(screen.getByLabelText('邮箱'), 'new@example.com')
    await user.type(screen.getByLabelText('密码'), 'secret1')
    await user.type(screen.getByLabelText('确认密码'), 'secret2')
    await user.click(screen.getByRole('button', { name: '注 册' }))
    expect(await screen.findByText('两次输入的密码不一致')).toBeInTheDocument()
    expect(registerMock).not.toHaveBeenCalled()
  })

  it('真实注册成功：authApi.register 回包 → toast 成功并切回登录页预填用户名', async () => {
    registerMock.mockResolvedValue({ userId: 42 })
    await fillAndSubmit()
    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('注册成功，请登录')
    )
    expect(registerMock).toHaveBeenCalledWith({
      username: 'new_user',
      email: 'new@example.com',
      password: 'secret1',
    })
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/login',
      search: { username: 'new_user' },
    })
  })

  it('403（注册开关关闭）：toast 提示 + 整页切引导态（返回登录）', async () => {
    registerMock.mockRejectedValue(
      apiError(203, 403, '注册未开放', '注册未开放')
    )
    await fillAndSubmit()
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        '当前站点未开放注册，请联系管理员开通账号'
      )
    )
    expect(await screen.findByText('当前站点未开放注册')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '返回登录' })
    ).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('400/409：toast 呈现服务端 detail 文案（注册失败：{detail}）', async () => {
    registerMock.mockRejectedValue(
      apiError(202, 409, '用户名已被使用')
    )
    await fillAndSubmit()
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('注册失败：用户名已被使用')
    )
  })
})
