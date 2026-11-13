import { describe, expect, it } from 'vitest'

import {
  AGENT_PROVIDER_STATUS,
  CONTEXT_WINDOW_SOURCE,
  CONTEXT_WINDOW_WARNING_ABOVE_CATALOG,
  DEFAULT_CONTEXT_WINDOW_BOUNDS,
  formatContextWindowTokens,
  isProviderNotConfiguredError,
  matchModelCatalogItem,
  resolveContextWindowPreview,
  validateContextWindowOverride,
  type ModelCatalog,
} from '@/domain/models/agentProvider'

const CATALOG: ModelCatalog = {
  fallbackContextWindow: 131_072,
  bounds: { ...DEFAULT_CONTEXT_WINDOW_BOUNDS },
  models: [
    { protocol: 'OPENAI_COMPATIBLE', match: 'deepseek-chat*', contextWindow: 65_536, maxOutputTokens: 8_192 },
    { protocol: 'OPENAI_COMPATIBLE', match: 'gpt-4o*', contextWindow: 128_000, maxOutputTokens: 16_384 },
    { protocol: 'ANTHROPIC', match: 'claude-sonnet-4*', contextWindow: 200_000, maxOutputTokens: 64_000 },
  ],
}

describe('matchModelCatalogItem', () => {
  it('按协议 + glob 命中（大小写不敏感）', () => {
    expect(matchModelCatalogItem(CATALOG, 'OPENAI_COMPATIBLE', 'DeepSeek-Chat')?.contextWindow).toBe(65_536)
    expect(matchModelCatalogItem(CATALOG, 'ANTHROPIC', 'claude-sonnet-4-20250514')?.contextWindow).toBe(200_000)
  })

  it('协议不匹配不命中', () => {
    expect(matchModelCatalogItem(CATALOG, 'ANTHROPIC', 'deepseek-chat')).toBeNull()
  })

  it('无目录 / 空模型名 → null（走兜底）', () => {
    expect(matchModelCatalogItem(undefined, 'OPENAI_COMPATIBLE', 'deepseek-chat')).toBeNull()
    expect(matchModelCatalogItem(CATALOG, 'OPENAI_COMPATIBLE', '  ')).toBeNull()
  })
})

describe('resolveContextWindowPreview', () => {
  it('未覆盖时取目录默认并标 MODEL_DEFAULT', () => {
    const preview = resolveContextWindowPreview(
      CATALOG,
      'OPENAI_COMPATIBLE',
      'gpt-4o-mini',
      null
    )
    expect(preview.source).toBe(CONTEXT_WINDOW_SOURCE.MODEL_DEFAULT)
    expect(preview.effectiveContextWindow).toBe(128_000)
    expect(preview.catalogMaxOutputTokens).toBe(16_384)
  })

  it('目录未命中时 128k 兜底并标 FALLBACK', () => {
    const preview = resolveContextWindowPreview(
      CATALOG,
      'OPENAI_COMPATIBLE',
      'unknown-model',
      null
    )
    expect(preview.source).toBe(CONTEXT_WINDOW_SOURCE.FALLBACK)
    expect(preview.effectiveContextWindow).toBe(131_072)
  })

  it('手动覆盖标 USER_OVERRIDE，且高于目录值时给出告警', () => {
    const normal = resolveContextWindowPreview(
      CATALOG,
      'OPENAI_COMPATIBLE',
      'deepseek-chat',
      32_768
    )
    expect(normal.source).toBe(CONTEXT_WINDOW_SOURCE.USER_OVERRIDE)
    expect(normal.effectiveContextWindow).toBe(32_768)
    expect(normal.warning).toBeNull()

    const above = resolveContextWindowPreview(
      CATALOG,
      'OPENAI_COMPATIBLE',
      'deepseek-chat',
      131_072
    )
    expect(above.warning).toBe(CONTEXT_WINDOW_WARNING_ABOVE_CATALOG)
    expect(above.effectiveContextWindow).toBe(131_072)
  })
})

describe('validateContextWindowOverride', () => {
  it('合法值通过（边界含端点）', () => {
    expect(validateContextWindowOverride(8_192)).toBeNull()
    expect(validateContextWindowOverride(32_768)).toBeNull()
    expect(validateContextWindowOverride(2_097_152)).toBeNull()
  })

  it('越界 / 未对齐 / 非整数报错', () => {
    expect(validateContextWindowOverride(8_191)).toContain('8k')
    expect(validateContextWindowOverride(2_098_176)).not.toBeNull()
    expect(validateContextWindowOverride(33_000)).toContain('1024')
    expect(validateContextWindowOverride(32_768.5)).not.toBeNull()
    expect(validateContextWindowOverride(Number.NaN)).not.toBeNull()
  })
})

describe('formatContextWindowTokens', () => {
  it('按 k / M 缩写', () => {
    expect(formatContextWindowTokens(131_072)).toBe('128k')
    expect(formatContextWindowTokens(1_048_576)).toBe('1M')
    expect(formatContextWindowTokens(2_097_152)).toBe('2M')
    expect(formatContextWindowTokens(1_500_000)).toBe('1.4M')
    expect(formatContextWindowTokens(null)).toBe('—')
  })
})

describe('isProviderNotConfiguredError', () => {
  it('识别错误码与错误串', () => {
    expect(isProviderNotConfiguredError('LLM_PROVIDER_NOT_CONFIGURED')).toBe(true)
    expect(
      isProviderNotConfiguredError('LLM_PROVIDER_NOT_CONFIGURED: 无可用供应商')
    ).toBe(true)
    expect(isProviderNotConfiguredError('AGENT_ERROR')).toBe(false)
    expect(isProviderNotConfiguredError(null)).toBe(false)
  })

  it('状态枚举常量与后端一致', () => {
    expect(AGENT_PROVIDER_STATUS.INVALID).toBe('INVALID')
  })
})
