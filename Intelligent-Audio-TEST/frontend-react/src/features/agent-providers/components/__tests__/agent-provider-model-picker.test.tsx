/**
 * 对话页「供应商 + 模型」选择器：供应商下拉可切换本轮供应商，
 * 模型下拉按所选供应商展示 /models 探测结果。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentProvider } from '@/domain/models/agentProvider'
import { AgentProviderModelPicker } from '@/features/agent-providers/components/agent-provider-model-picker'

function provider(overrides: Partial<AgentProvider>): AgentProvider {
  return {
    id: 'p-1',
    name: '火山AI',
    protocol: 'OPENAI_COMPATIBLE',
    baseUrl: 'http://a.local/v1',
    model: 'deepseek-v4-flash',
    apiKeyMask: 'sk-****1111',
    contextWindow: null,
    contextWindowSource: 'FALLBACK',
    effectiveContextWindow: 65_536,
    catalogContextWindow: null,
    catalogMaxOutputTokens: null,
    contextWindowWarning: null,
    contextWindowWarningMessage: null,
    isDefault: true,
    status: 'ACTIVE',
    lastVerifiedAt: null,
    createdAt: null,
    updatedAt: null,
    ...overrides,
  }
}

const PROVIDERS = [
  provider({}),
  provider({
    id: 'p-2',
    name: 'DeepSeek',
    model: 'deepseek-chat',
    isDefault: false,
  }),
]

const listAgentProviders = vi.fn(async () => PROVIDERS)
const discoverAgentProviderModels = vi.fn(
  async (input: { providerId?: string }) => ({
    ok: true,
    code: 'PROVIDER_MODELS_OK',
    message: 'ok',
    models:
      input.providerId === 'p-2'
        ? ['deepseek-chat', 'deepseek-reasoner']
        : ['deepseek-v4-flash', 'deepseek-v4-pro'],
  })
)

vi.mock('@/infrastructure/api/agentProviderApi', () => ({
  listAgentProviders: () => listAgentProviders(),
  discoverAgentProviderModels: (input: { providerId?: string }) =>
    discoverAgentProviderModels(input),
  createAgentProvider: vi.fn(),
  deleteAgentProvider: vi.fn(),
  fetchModelCatalog: vi.fn(),
  setDefaultAgentProvider: vi.fn(),
  updateAgentProvider: vi.fn(),
  verifyAgentProvider: vi.fn(),
}))

function renderPicker() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const onProviderChange = vi.fn()
  const onModelChange = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <AgentProviderModelPicker
        onModelChange={onModelChange}
        onProviderChange={onProviderChange}
      />
    </QueryClientProvider>
  )
  return { onProviderChange, onModelChange }
}

describe('AgentProviderModelPicker', () => {
  beforeEach(() => {
    listAgentProviders.mockClear()
    discoverAgentProviderModels.mockClear()
  })

  it('默认展示默认供应商，模型下拉可选探测结果', async () => {
    const user = userEvent.setup()
    const { onModelChange } = renderPicker()

    const providerTrigger = await screen.findByRole('combobox', {
      name: '选择供应商',
    })
    await waitFor(() => expect(providerTrigger).toHaveTextContent('火山AI'))

    const modelTrigger = await screen.findByRole('combobox', { name: '选择模型' })
    await waitFor(() =>
      expect(modelTrigger).toHaveTextContent('deepseek-v4-flash')
    )
    await user.click(modelTrigger)
    await user.click(await screen.findByRole('option', { name: 'deepseek-v4-pro' }))

    expect(onModelChange).toHaveBeenCalledWith('deepseek-v4-pro')
  })

  it('切换供应商会回传所选供应商 id', async () => {
    const user = userEvent.setup()
    const { onProviderChange } = renderPicker()

    const providerTrigger = await screen.findByRole('combobox', {
      name: '选择供应商',
    })
    await user.click(providerTrigger)
    await user.click(await screen.findByRole('option', { name: 'DeepSeek' }))

    expect(onProviderChange).toHaveBeenCalledWith('p-2')
  })
})
