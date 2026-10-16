/**
 * 母版 A 保存链装配测试（INT-489 返修③回归）：
 * 点「重置」回基线并弹 toast「表单已重置为已保存的值」（05_系统设置.md §1.3/§6）。
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
import { toast } from 'sonner'
import { describe, expect, it, vi } from 'vitest'

import { SettingsPageProvider } from '../components/settings-page-context'
import { SettingsFormPage } from '../components/settings-form-page'

const baseline = { name: '旧名' }
const optionKey = (field: keyof typeof baseline) => `site.${String(field)}`

function SettingsFormHost({ children }: { children: ReactNode }) {
  const [actionsContainer, setActionsContainer] = useState<HTMLDivElement | null>(null)
  return (
    <SettingsPageProvider actionsContainer={actionsContainer}>
      <div data-testid='actions-slot' ref={setActionsContainer} />
      {children}
    </SettingsPageProvider>
  )
}

async function renderSettingsForm(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <QueryClientProvider client={queryClient}>
          <SettingsFormHost>{ui}</SettingsFormHost>
        </QueryClientProvider>
      ),
    }),
    history: createMemoryHistory({ initialEntries: ['/system-settings/site/info'] }),
  })
  await router.load()
  render(<RouterProvider router={router} />)
}

describe('SettingsFormPage', () => {
  it('改字段后脏态出现，点「重置」回基线并弹重置 toast', async () => {
    const toastSuccess = vi.spyOn(toast, 'success')
    const user = userEvent.setup()

    await renderSettingsForm(
      <SettingsFormPage<typeof baseline>
        baseline={baseline}
        optionKey={optionKey}
      >
        {(draft, setField) => (
          <input
            aria-label='名称'
            value={draft.name}
            onChange={(event) => setField('name', event.target.value)}
          />
        )}
      </SettingsFormPage>
    )

    const input = screen.getByLabelText('名称')
    expect(input).toHaveValue('旧名')

    // 干净态：重置/保存按钮禁用
    expect(screen.getByRole('button', { name: '重置' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '保存更改' })).toBeDisabled()

    await user.clear(input)
    await user.type(input, '新名')
    expect(screen.getByRole('button', { name: '重置' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '重置' }))
    expect(input).toHaveValue('旧名')
    expect(screen.getByRole('button', { name: '重置' })).toBeDisabled()
    expect(toastSuccess).toHaveBeenCalledWith('表单已重置为已保存的值')
  })
})
