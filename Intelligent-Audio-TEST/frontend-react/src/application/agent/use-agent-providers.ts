/**
 * 模型供应商 query + mutation（application 层；INT-2493 / §6.4 / §11）。
 *
 * 单一缓存口径：供应商列表与模型目录各一个 query key；
 * 设为默认 / 删除 / 验证 / 新增 / 编辑成功后一律 invalidateQueries，
 * 供应商列表、会话页 provider 状态摘要、默认标记三处同步刷新（不做局部改状态）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type {
  AgentProvider,
  AgentProviderInput,
  AgentProviderVerification,
  ModelCatalog,
} from '@/domain/models/agentProvider'
import {
  createAgentProvider,
  deleteAgentProvider,
  fetchModelCatalog,
  listAgentProviders,
  setDefaultAgentProvider,
  updateAgentProvider,
  verifyAgentProvider,
} from '@/infrastructure/api/agentProviderApi'
import { ApiError } from '@/infrastructure/api/api-error'

/** 供应商列表缓存键（列表 / 会话页摘要共用） */
export const AGENT_PROVIDERS_QUERY_KEY = ['agent', 'providers'] as const
/** 模型目录缓存键（表单预填） */
export const AGENT_MODEL_CATALOG_QUERY_KEY = ['agent', 'model-catalog'] as const

/** 页面可直接展示的错误文案（ApiError 已含中文归一） */
function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.userMessage) return error.userMessage
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export function useAgentProvidersQuery(options: { enabled?: boolean } = {}) {
  return useQuery<AgentProvider[]>({
    queryKey: [...AGENT_PROVIDERS_QUERY_KEY],
    queryFn: listAgentProviders,
    staleTime: 15_000,
    retry: false,
    enabled: options.enabled ?? true,
  })
}

export function useAgentModelCatalogQuery() {
  return useQuery<ModelCatalog>({
    queryKey: [...AGENT_MODEL_CATALOG_QUERY_KEY],
    queryFn: fetchModelCatalog,
    // 目录是后端静态配置，一次读取后保持；页面重进不重复请求
    staleTime: Infinity,
    retry: false,
  })
}

export function useAgentProviderMutations() {
  const queryClient = useQueryClient()

  const invalidateProviders = () =>
    void queryClient.invalidateQueries({ queryKey: AGENT_PROVIDERS_QUERY_KEY })

  const create = useMutation({
    mutationFn: (input: AgentProviderInput) => createAgentProvider(input),
    onSuccess: () => {
      toast.success('模型供应商已添加')
      invalidateProviders()
    },
    onError: (error: unknown) => {
      toast.error(toMessage(error, '添加模型供应商失败'))
    },
  })

  const update = useMutation({
    mutationFn: (args: { id: string; input: AgentProviderInput }) =>
      updateAgentProvider(args.id, args.input),
    onSuccess: () => {
      toast.success('模型供应商已保存')
      invalidateProviders()
    },
    onError: (error: unknown) => {
      toast.error(toMessage(error, '保存模型供应商失败'))
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteAgentProvider(id),
    onSuccess: () => {
      toast.success('模型供应商已删除')
      invalidateProviders()
    },
    onError: (error: unknown) => {
      toast.error(toMessage(error, '删除模型供应商失败'))
    },
  })

  const setDefault = useMutation({
    mutationFn: (id: string) => setDefaultAgentProvider(id),
    onSuccess: () => {
      toast.success('已设为默认模型供应商')
      invalidateProviders()
    },
    onError: (error: unknown) => {
      toast.error(toMessage(error, '设置默认供应商失败'))
    },
  })

  const verify = useMutation({
    mutationFn: (id: string): Promise<AgentProviderVerification> =>
      verifyAgentProvider(id),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success('连通性验证通过')
      } else {
        toast.error(result.message || '连通性验证失败')
      }
      // 验证会更新 status / last_verified_at，回读列表（同一 query key）
      invalidateProviders()
    },
    onError: (error: unknown) => {
      toast.error(toMessage(error, '连通性验证失败'))
    },
  })

  return { create, update, remove, setDefault, verify, invalidateProviders }
}

/** 当前默认供应商（会话页摘要与供应商列表共用同一缓存） */
export function pickDefaultProvider(
  providers: AgentProvider[] | undefined
): AgentProvider | null {
  if (!providers || providers.length === 0) return null
  return providers.find((provider) => provider.isDefault) ?? providers[0] ?? null
}

/** 是否存在可用的供应商（有记录且非 INVALID/DELETED） */
export function hasUsableProvider(
  providers: AgentProvider[] | undefined
): boolean {
  return Boolean(
    providers?.some(
      (provider) => provider.status !== 'INVALID' && provider.status !== 'DELETED'
    )
  )
}
