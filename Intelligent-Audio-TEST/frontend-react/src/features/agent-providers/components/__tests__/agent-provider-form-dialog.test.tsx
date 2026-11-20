/**
 * 供应商表单「自动发现模型」回归：
 * 1. 用当前表单的协议 / Base URL / Key 调探测接口，并把首个模型回填；
 * 2. Base URL 非法时不发请求，直接提示地址错误。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AgentProviderFormDialog } from '../agent-provider-form-dialog'

function renderDialog() {
  const onDiscoverModels = vi.fn().mockResolvedValue({
    ok: true,
    code: 'PROVIDER_MODELS_OK',
    message: '发现 2 个模型',
    models: ['deepseek-chat', 'deepseek-reasoner'],
  })
  const onSubmit = vi.fn().mockResolvedValue(true)
  render(
    <AgentProviderFormDialog
      catalog={undefined}
      onDiscoverModels={onDiscoverModels}
      onOpenChange={vi.fn()}
      onSubmit={onSubmit}
      open
      pending={false}
      provider={null}
    />
  )
  return { onDiscoverModels, onSubmit }
}

describe('AgentProviderFormDialog 自动发现模型', () => {
  it('按表单协议 / Base URL / Key 探测并回填首个模型', async () => {
    const { onDiscoverModels } = renderDialog()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Base URL'), 'https://api.deepseek.com/v1')
    await user.type(screen.getByLabelText('API Key'), 'sk-test')
    await user.click(screen.getByRole('button', { name: /自动发现模型/ }))

    await waitFor(() => expect(onDiscoverModels).toHaveBeenCalledTimes(1))
    expect(onDiscoverModels).toHaveBeenCalledWith({
      providerId: undefined,
      protocol: 'OPENAI_COMPATIBLE',
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: 'sk-test',
    })
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: '模型名' })).toHaveTextContent(
        'deepseek-chat'
      )
    )
  })

  it('Base URL 非法时不探测并提示地址错误', async () => {
    const { onDiscoverModels } = renderDialog()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Base URL'), 'api.deepseek.com')
    await user.click(screen.getByRole('button', { name: /自动发现模型/ }))

    expect(await screen.findByText('Base URL 必须是 http(s) 地址')).toBeInTheDocument()
    expect(onDiscoverModels).not.toHaveBeenCalled()
  })

  it('发现的模型可直接下拉选择，并可切回手动输入', async () => {
    renderDialog()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Base URL'), 'https://api.deepseek.com/v1')
    await user.type(screen.getByLabelText('API Key'), 'sk-test')
    await user.click(screen.getByRole('button', { name: /自动发现模型/ }))

    const trigger = await screen.findByRole('combobox', { name: '模型名' })
    await user.click(trigger)
    const option = await screen.findByRole('option', { name: 'deepseek-reasoner' })
    await user.click(option)

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: '模型名' })).toHaveTextContent(
        'deepseek-reasoner'
      )
    )

    await user.click(screen.getByRole('button', { name: '手动输入模型名' }))
    expect(screen.getByLabelText('模型名')).toHaveValue('deepseek-reasoner')
  })
})
