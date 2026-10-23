/**
 * OAuth 提供方新建弹窗表单校验测试（INT-1564）：
 * §6 口径——名称/Slug/Client ID/Client Secret（新建必填、编辑留空保留原值）/
 * 授权端点/Token 端点/用户信息端点必填，Slug 仅小写字母/数字/连字符；
 * 校验失败不发请求并给字段级提示。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { OAuthProvidersPage } from '@/features/system-settings/auth/oauth-providers-page'

const { createMutate } = vi.hoisted(() => ({ createMutate: vi.fn() }))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ user: null, hasPermission: () => true, hasAnyPermission: () => true }),
}))

vi.mock('@/application/oauth/use-oauth-providers', () => ({
  useOAuthProvidersQuery: () => ({ isLoading: false, isError: false, data: [] }),
  useOAuthProviderMutations: () => ({
    createProvider: { mutate: createMutate, isPending: false },
    updateProvider: { mutate: vi.fn(), isPending: false },
    deleteProvider: { mutate: vi.fn(), isPending: false },
    discoverEndpoints: vi.fn(),
  }),
}))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  render(
    <QueryClientProvider client={client}>
      <OAuthProvidersPage />
    </QueryClientProvider>
  )
}

async function openCreateDialog() {
  const user = userEvent.setup()
  renderPage()
  await user.click(screen.getByRole('button', { name: /添加提供方/ }))
  await screen.findByText('新建提供方')
  return user
}

describe('OAuth 提供方新建弹窗校验', () => {
  it('Client Secret 标必填，空必填项提交被拦截并给字段级提示（不发请求）', async () => {
    const user = await openCreateDialog()

    const secretLabel = document.querySelector('label[for="oauth-client-secret"]')
    expect(secretLabel).not.toBeNull()
    expect(within(secretLabel as HTMLElement).getByText('*')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '保存' }))

    for (const message of [
      '请输入名称',
      '请输入 Slug',
      '请输入 Client ID',
      '请输入 Client Secret',
      '请输入授权端点',
      '请输入 Token 端点',
      '请输入用户信息端点',
    ]) {
      expect(screen.getByText(message)).toBeInTheDocument()
    }
    expect(document.getElementById('oauth-client-secret')).toHaveAttribute(
      'aria-invalid',
      'true'
    )
    expect(createMutate).not.toHaveBeenCalled()
  })

  it('Slug 非法值拦截，改合法后提交载荷正确', async () => {
    const user = await openCreateDialog()

    await user.type(screen.getByLabelText(/名称/), '接线测试_OAuth')
    await user.type(screen.getByLabelText(/Slug/), 'Footer_Test')
    await user.type(screen.getByLabelText(/Client ID/), 'client-abc')
    await user.type(screen.getByLabelText(/Client Secret/), 'secret-abc')
    await user.type(screen.getByLabelText(/授权端点/), 'https://idp.example.com/authorize')
    await user.type(screen.getByLabelText(/Token 端点/), 'https://idp.example.com/token')
    await user.type(screen.getByLabelText(/用户信息端点/), 'https://idp.example.com/userinfo')

    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(screen.getByText('仅允许小写字母、数字与连字符')).toBeInTheDocument()
    expect(createMutate).not.toHaveBeenCalled()

    const slugInput = screen.getByLabelText(/Slug/)
    await user.clear(slugInput)
    await user.type(slugInput, 'footer-test')
    expect(screen.queryByText('仅允许小写字母、数字与连字符')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(createMutate).toHaveBeenCalledTimes(1)
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '接线测试_OAuth',
        slug: 'footer-test',
        clientId: 'client-abc',
        clientSecret: 'secret-abc',
        authorizationEndpoint: 'https://idp.example.com/authorize',
        tokenEndpoint: 'https://idp.example.com/token',
        userinfoEndpoint: 'https://idp.example.com/userinfo',
      })
    )
  })
})
