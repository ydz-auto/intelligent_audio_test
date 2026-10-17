/**
 * use-llm-providers 单测（INT-598 §3.11）：供应商清单 localStorage
 * iatp:ai-chat:v1:providers 读写 + CRUD + 默认回落（首个添加为默认、删除默认回落首个）。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useLlmProviders } from '@/features/ai-chat/hooks/use-llm-providers'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'

const DRAFT = { name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', apiKey: 'sk-test', models: ['gpt-4o'] }

describe('useLlmProviders', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('空初始：无供应商、无默认', () => {
    const { result } = renderHook(() => useLlmProviders())
    expect(result.current.providers).toEqual([])
    expect(result.current.defaultProvider).toBeNull()
  })

  it('添加首个供应商即默认，并持久化 localStorage', () => {
    const { result } = renderHook(() => useLlmProviders())
    act(() => {
      result.current.addProvider(DRAFT)
    })
    expect(result.current.providers).toHaveLength(1)
    expect(result.current.providers[0].isDefault).toBe(true)
    expect(result.current.defaultProvider?.name).toBe('OpenAI')

    const saved = aiChatPrefs.loadProviders()
    expect(saved).toHaveLength(1)
    expect(saved?.[0].baseUrl).toBe('https://api.openai.com/v1')
  })

  it('添加第二个供应商：默认仍为首个；setDefault 改默认', () => {
    const { result } = renderHook(() => useLlmProviders())
    act(() => {
      result.current.addProvider(DRAFT)
      result.current.addProvider({
        name: 'DeepSeek',
        baseUrl: 'https://api.deepseek.com/v1',
        apiKey: 'sk-ds',
        models: ['deepseek-chat'],
      })
    })
    expect(result.current.defaultProvider?.name).toBe('OpenAI')

    const secondId = result.current.providers[1].id
    act(() => {
      result.current.setDefaultProvider(secondId)
    })
    expect(result.current.defaultProvider?.name).toBe('DeepSeek')
  })

  it('删除默认供应商后回落首个为默认', () => {
    const { result } = renderHook(() => useLlmProviders())
    act(() => {
      result.current.addProvider(DRAFT)
      result.current.addProvider({
        name: 'DeepSeek',
        baseUrl: 'https://api.deepseek.com/v1',
        apiKey: 'sk-ds',
        models: ['deepseek-chat'],
      })
    })
    const firstId = result.current.providers[0].id
    act(() => {
      result.current.removeProvider(firstId)
    })
    expect(result.current.providers).toHaveLength(1)
    expect(result.current.defaultProvider?.name).toBe('DeepSeek')
    expect(result.current.defaultProvider?.isDefault).toBe(true)
  })

  it('编辑供应商字段（updateProvider 合并）', () => {
    const { result } = renderHook(() => useLlmProviders())
    act(() => {
      result.current.addProvider(DRAFT)
    })
    const id = result.current.providers[0].id
    act(() => {
      result.current.updateProvider(id, { name: 'OpenAI 新版', models: ['gpt-4.1'] })
    })
    expect(result.current.providers[0].name).toBe('OpenAI 新版')
    expect(result.current.providers[0].models).toEqual(['gpt-4.1'])
    expect(result.current.providers[0].apiKey).toBe('sk-test')
  })
})
