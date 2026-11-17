/**
 * 认证方式分区 · 邀请码注册（回归）：
 * 开关关闭时不展开邀请码输入；开启后保存写入正确的 snake_case KV 键
 * （auth.invite_code_registration / auth.invite_code）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthMethodSettings } from '@/domain/models/option'
import { AuthMethodsPage } from '../methods-page'
import { SettingsPageProvider } from '../../components/settings-page-context'

const { mutateMock } = vi.hoisted(() => ({ mutateMock: vi.fn() }))

vi.mock('@/application/settings/use-update-option', () => ({
  useUpdateOption: () => ({ mutate: mutateMock, isPending: false }),
}))

const baseline: AuthMethodSettings = {
  passwordLogin: true,
  registration: true,
  emailVerification: false,
  inviteCodeRegistration: false,
  inviteCode: '',
}

function Host({ children }: { children: ReactNode }) {
  const [actionsContainer, setActionsContainer] = useState<HTMLDivElement | null>(
    null
  )
  return (
    <SettingsPageProvider actionsContainer={actionsContainer}>
      <div data-testid='actions-slot' ref={setActionsContainer} />
      {children}
    </SettingsPageProvider>
  )
}

async function renderPage(defaultValues: AuthMethodSettings = baseline) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <QueryClientProvider client={client}>
          <Host>
            <AuthMethodsPage defaultValues={defaultValues} />
          </Host>
        </QueryClientProvider>
      ),
    }),
    history: createMemoryHistory({
      initialEntries: ['/system-settings/auth/methods'],
    }),
  })
  await router.load()
  render(<RouterProvider router={router} />)
}

describe('认证方式 · 邀请码注册', () => {
  beforeEach(() => {
    mutateMock.mockReset()
  })

  it('开关关闭时不渲染邀请码输入', async () => {
    await renderPage()
    expect(screen.queryByLabelText('邀请码')).not.toBeInTheDocument()
  })

  it('开启后展开邀请码输入，保存写入正确 KV 键', async () => {
    const user = userEvent.setup()
    await renderPage()

    await user.click(screen.getByRole('switch', { name: /邀请码注册/ }))
    await user.type(await screen.findByLabelText('邀请码'), 'INV-2026')
    await user.click(screen.getByRole('button', { name: '保存更改' }))

    expect(mutateMock).toHaveBeenCalledWith([
      { key: 'auth.invite_code_registration', value: true },
      { key: 'auth.invite_code', value: 'INV-2026' },
    ])
  })
})
