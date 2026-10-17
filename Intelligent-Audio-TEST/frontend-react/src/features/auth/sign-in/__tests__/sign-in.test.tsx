/**
 * 登录页 SignIn 测试（认证接线 INT-606，12_登录与错误页.md §3.1）：
 * AUTH_MODE=off 时顶部渲染开放模式 Alert +「进入工作台」钮；非 off 模式不渲染。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SignIn } from '@/features/auth/sign-in'
import {
  AUTH_MODE_OFF_ALERT_TEXT,
  AUTH_MODE_OFF_ENTER_ACTION,
} from '@/features/auth/constants'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    // 测试不挂 RouterProvider，Link 降级为普通 <a>（仅验证 Alert 呈现）
    Link: ({
      children,
      to,
      ...props
    }: React.ComponentProps<'a'> & { to?: string }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  }
})

vi.mock('@/application/auth/use-auth-mode', () => ({
  AUTH_MODE: { OFF: 'off', DEV: 'dev', PROD: 'prod' },
  useAuthMode: () => ({ data: 'off' }),
}))

vi.mock('@/application/auth/use-public-oauth-providers', () => ({
  usePublicOAuthProviders: () => ({ data: [] }),
}))

function renderSignIn() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  render(
    <QueryClientProvider client={client}>
      <SignIn />
    </QueryClientProvider>
  )
}

describe('SignIn AUTH_MODE=off 兼容', () => {
  it('off 模式：渲染开放模式 Alert + 进入工作台按钮，点击跳工作台', async () => {
    renderSignIn()
    expect(screen.getByText(AUTH_MODE_OFF_ALERT_TEXT)).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(
      screen.getByRole('button', { name: AUTH_MODE_OFF_ENTER_ACTION })
    )
    expect(navigateMock).toHaveBeenCalledWith({ to: '/dashboard' })
  })
})
