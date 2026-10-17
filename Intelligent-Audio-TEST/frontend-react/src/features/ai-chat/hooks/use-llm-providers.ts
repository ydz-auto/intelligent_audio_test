/**
 * LLM 供应商清单 hook（interfaces 层 hooks；08_AI对话页.md §3.11）。
 * localStorage `iatp:ai-chat:v1:providers` 读写 + CRUD + 测试连接 + 默认回落。
 * 用户自管（chatbox 式）：供应商仅存本机，不上传平台后端；默认供应商=首个添加（§3.11）。
 */
import { useCallback, useEffect, useState } from 'react'

import type { LlmProvider } from '@/domain/models/aiChat'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'
import {
  fetchProviderModels,
  testProviderConnection,
} from '@/infrastructure/api/llmProviderApi'

export type LlmProviderDraft = Pick<LlmProvider, 'name' | 'baseUrl' | 'apiKey' | 'models'>

function createProviderId(): string {
  return `provider-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function useLlmProviders() {
  const [providers, setProviders] = useState<LlmProvider[]>(() => {
    const saved = aiChatPrefs.loadProviders()
    if (saved && saved.length > 0) return saved
    return []
  })

  // 持久化（§3.11 存储：envelope{version,data}，密钥仅存本机）
  useEffect(() => {
    aiChatPrefs.saveProviders(providers)
  }, [providers])

  /** 默认供应商：isDefault 标记优先，否则首个（§3.11 默认=首个添加） */
  const defaultProvider = providers.find((p) => p.isDefault) ?? providers[0] ?? null

  const addProvider = useCallback((draft: LlmProviderDraft) => {
    const next: LlmProvider = {
      id: createProviderId(),
      name: draft.name,
      baseUrl: draft.baseUrl,
      apiKey: draft.apiKey,
      models: draft.models,
      // 首个添加默认为默认供应商（§3.11）
      isDefault: false,
    }
    setProviders((prev) => {
      const isFirst = prev.length === 0
      return [...prev, { ...next, isDefault: isFirst || next.isDefault }]
    })
    return next
  }, [])

  const updateProvider = useCallback((id: string, draft: Partial<LlmProviderDraft>) => {
    setProviders((prev) =>
      prev.map((p) => (p.id === id ? { ...p, ...draft } : p))
    )
  }, [])

  const removeProvider = useCallback((id: string) => {
    setProviders((prev) => {
      const next = prev.filter((p) => p.id !== id)
      // 删除默认供应商后回落首个为默认（§3.11 行为）
      if (next.length > 0 && !next.some((p) => p.isDefault)) {
        next[0] = { ...next[0], isDefault: true }
      }
      return next
    })
  }, [])

  const setDefaultProvider = useCallback((id: string) => {
    setProviders((prev) =>
      prev.map((p) => ({ ...p, isDefault: p.id === id }))
    )
  }, [])

  /** 测试连接（§3.11 表单「测试连接」；真实 GET {baseUrl}/models——2026-10-17 审计 P2-1 返修） */
  const handleTestConnection = useCallback(
    (draft: Pick<LlmProvider, 'baseUrl' | 'apiKey'>) => testProviderConnection(draft),
    []
  )

  /** 自动获取模型列表（§3.11 表单「自动获取模型列表」；真实 GET {baseUrl}/models） */
  const handleFetchModels = useCallback(
    (draft: Pick<LlmProvider, 'baseUrl' | 'apiKey'>) => fetchProviderModels(draft),
    []
  )

  return {
    providers,
    defaultProvider,
    addProvider,
    updateProvider,
    removeProvider,
    setDefaultProvider,
    testConnection: handleTestConnection,
    fetchModels: handleFetchModels,
  }
}
