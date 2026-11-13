import { describe, expect, it } from 'vitest'

import {
  toAgentProvider,
  toAgentProviderVerification,
  toAgentProviders,
  toCreateProviderPayload,
  toModelCatalog,
  toUpdateProviderPayload,
  type AgentProviderDto,
} from '@/infrastructure/dto/agentProvider.dto'

const RAW: AgentProviderDto = {
  id: 'p-1',
  owner_id: 7,
  tenant_id: 'default',
  name: 'DeepSeek 主力',
  protocol: 'OPENAI_COMPATIBLE',
  base_url: 'https://api.deepseek.com/v1',
  model: 'deepseek-chat',
  api_key_mask: 'sk-****abcd',
  context_window: 32_768,
  context_window_source: 'USER_OVERRIDE',
  effective_context_window: 32_768,
  catalog_context_window: 65_536,
  catalog_max_output_tokens: 8_192,
  context_window_warning: null,
  context_window_warning_message: null,
  is_default: true,
  status: 'ACTIVE',
  last_verified_at: '2026-11-13T04:00:00',
  created_at: '2026-11-13T03:00:00',
  updated_at: '2026-11-13T04:00:00',
}

describe('toAgentProvider', () => {
  it('snake_case → camelCase，且只保留掩码', () => {
    const provider = toAgentProvider(RAW)
    expect(provider).toMatchObject({
      id: 'p-1',
      name: 'DeepSeek 主力',
      protocol: 'OPENAI_COMPATIBLE',
      baseUrl: 'https://api.deepseek.com/v1',
      model: 'deepseek-chat',
      apiKeyMask: 'sk-****abcd',
      contextWindow: 32_768,
      contextWindowSource: 'USER_OVERRIDE',
      effectiveContextWindow: 32_768,
      catalogContextWindow: 65_536,
      catalogMaxOutputTokens: 8_192,
      isDefault: true,
      status: 'ACTIVE',
      lastVerifiedAt: '2026-11-13T04:00:00',
    })
    expect(JSON.stringify(provider)).not.toContain('api_key_ciphertext')
  })

  it('缺省字段归一（名称回退模型名 / 未识别状态按可用）', () => {
    const provider = toAgentProvider({
      id: 'p-2',
      base_url: 'http://x.local',
      model: 'm',
      api_key_mask: '',
      protocol: 'unknown',
      status: 'unknown',
      context_window: null,
    })
    expect(provider.name).toBe('m')
    expect(provider.protocol).toBe('OPENAI_COMPATIBLE')
    expect(provider.status).toBe('ACTIVE')
    expect(provider.contextWindow).toBeNull()
    expect(provider.contextWindowSource).toBe('FALLBACK')
  })

  it('列表缺 items 时返回空数组', () => {
    expect(toAgentProviders({})).toEqual([])
    expect(toAgentProviders(null)).toEqual([])
  })
})

describe('toModelCatalog', () => {
  it('映射目录条目与边界', () => {
    const catalog = toModelCatalog({
      fallback_context_window: 131_072,
      bounds: { min: 8_192, max: 2_097_152, alignment: 1_024 },
      models: [
        {
          protocol: 'OPENAI_COMPATIBLE',
          match: 'deepseek-chat*',
          context_window: 65_536,
          max_output_tokens: 8_192,
        },
      ],
    })
    expect(catalog.fallbackContextWindow).toBe(131_072)
    expect(catalog.bounds).toEqual({ min: 8_192, max: 2_097_152, alignment: 1_024 })
    expect(catalog.models[0]).toEqual({
      protocol: 'OPENAI_COMPATIBLE',
      match: 'deepseek-chat*',
      contextWindow: 65_536,
      maxOutputTokens: 8_192,
    })
  })

  it('空响应走 128k 兜底与默认边界', () => {
    const catalog = toModelCatalog({})
    expect(catalog.fallbackContextWindow).toBe(131_072)
    expect(catalog.bounds).toEqual({ min: 8_192, max: 2_097_152, alignment: 1_024 })
    expect(catalog.models).toEqual([])
  })
})

describe('toCreateProviderPayload / toUpdateProviderPayload', () => {
  const input = {
    name: ' 主用 ',
    protocol: 'ANTHROPIC' as const,
    baseUrl: ' https://api.anthropic.com ',
    model: 'claude-sonnet-4-20250514',
    apiKey: ' sk-ant-xxx ',
    contextWindow: 32_768,
  }

  it('新建载荷：snake_case + trim，Key 只在请求体内', () => {
    expect(toCreateProviderPayload(input)).toEqual({
      name: '主用',
      protocol: 'ANTHROPIC',
      base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-20250514',
      api_key: 'sk-ant-xxx',
      context_window: 32_768,
    })
  })

  it('编辑留空 Key 不发送 api_key（原 Key 不变）', () => {
    const payload = toUpdateProviderPayload({ ...input, apiKey: '   ' })
    expect(payload).not.toHaveProperty('api_key')
    expect(payload.context_window).toBe(32_768)
  })

  it('编辑填了 Key 才发送', () => {
    expect(toUpdateProviderPayload(input).api_key).toBe('sk-ant-xxx')
  })

  it('contextWindow=null 表示恢复默认并原样发送', () => {
    expect(
      toUpdateProviderPayload({ ...input, contextWindow: null })
    ).toHaveProperty('context_window', null)
  })
})

describe('toAgentProviderVerification', () => {
  it('验证结果映射（ok=false 时保留原因）', () => {
    const result = toAgentProviderVerification({
      provider_id: 'p-1',
      ok: false,
      code: 'PROVIDER_AUTH_FAILED',
      message: '认证失败：无效的 API Key',
      status: 'INVALID',
      last_verified_at: '2026-11-13T05:00:00',
    })
    expect(result).toEqual({
      providerId: 'p-1',
      ok: false,
      code: 'PROVIDER_AUTH_FAILED',
      message: '认证失败：无效的 API Key',
      status: 'INVALID',
      lastVerifiedAt: '2026-11-13T05:00:00',
    })
  })
})
