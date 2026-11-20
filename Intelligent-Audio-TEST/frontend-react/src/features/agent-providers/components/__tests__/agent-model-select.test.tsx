/**
 * 对话页模型下拉：默认供应商的可用模型（/models 探测）全量可选，
 * 选择结果通过 onModelChange 回传；未选择时展示供应商默认模型。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentProvider } from '@/domain/models/agentProvider'
import { AgentModelSelect } from '@/features/agent-providers/components/agent-model-select'

const PROVIDER: AgentProvider = {
  id: 'p-1',
  name: '火山AI',
  protocol: 'OPENAI_COMPATIBLE',
  baseUrl: 'http://host.docker.internal:3000/v1',
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
}

const listAgentProviders = vi.fn(async () => [PROVIDER])
const discoverAgentProviderModels = vi.fn(async () => ({
  ok: true,
  code: 'PROVIDER_MODELS_OK',
  message: '发现 3 个模型',
  models: ['deepseek-v4-flash', 'deepseek-v4-pro', 'glm-5.3'],
}))

vi.mock('@/infrastructure/api/agentProviderApi', () => ({
  listAgentProviders: () => listAgentProviders(),
  discoverAgentProviderModels: () => discoverAgentProviderModels(),
  createAgentProvider: vi.fn(),
  deleteAgentProvider: vi.fn(),
  fetchModelCatalog: vi.fn(),
  setDefaultAgentProvider: vi.fn(),
  updateAgentProvider: vi.fn(),
  verifyAgentProvider: vi.fn(),
}))

function renderSelect(onModelChange = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <AgentModelSelect onModelChange={onModelChange} />
    </QueryClientProvider>
  )
  return { onModelChange }
}

describe('AgentModelSelect', () => {
  beforeEach(() => {
    listAgentProviders.mockClear()
    discoverAgentProviderModels.mockClear()
  })

  it('默认展示供应商模型，展开后可选择探测到的其他模型', async () => {
    const user = userEvent.setup()
    const { onModelChange } = renderSelect()

    const trigger = await screen.findByRole('combobox', { name: '选择模型' })
    await waitFor(() => expect(trigger).toHaveTextContent('deepseek-v4-flash'))

    await user.click(trigger)
    await user.click(await screen.findByRole('option', { name: 'glm-5.3' }))

    expect(onModelChange).toHaveBeenCalledWith('glm-5.3')
  })

  it('探测结果为空时至少保留供应商配置的模型', async () => {
    discoverAgentProviderModels.mockResolvedValueOnce({
      ok: false,
      code: 'PROVIDER_UNREACHABLE',
      message: '无法连接供应商',
      models: [],
    })
    const user = userEvent.setup()
    renderSelect()

    const trigger = await screen.findByRole('combobox', { name: '选择模型' })
    await waitFor(() => expect(trigger).toHaveTextContent('deepseek-v4-flash'))
    await user.click(trigger)
    expect(screen.getAllByRole('option')).toHaveLength(1)
  })
})
