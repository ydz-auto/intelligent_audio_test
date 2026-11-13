/**
 * 模型供应商 API（infrastructure 层；doc/agent化/07_单Agent_Skills落地方案.md
 * §6.4 / §11 provider API，INT-2488 后端契约）。
 *
 * 端点（网关透明转发，无 {success,data} 信封）：
 *   GET    /agent/providers
 *   POST   /agent/providers
 *   PUT    /agent/providers/{id}
 *   DELETE /agent/providers/{id}
 *   POST   /agent/providers/{id}/verify
 *   POST   /agent/providers/{id}/set-default
 *   GET    /agent/model-catalog
 *
 * 传输：普通请求走 client.ts（JWT / 错误码归一）；本文件只产出 camelCase 领域对象，
 * snake_case 转换在 infrastructure/dto/agentProvider.dto.ts。
 * 注意：verify 响应顶层带 `code`（'OK' 等字符串）字段，client 的信封解包会把它
 * 误判成业务信封，故 verify 显式关闭 unwrapResponse。
 */
import type {
  AgentProvider,
  AgentProviderInput,
  AgentProviderVerification,
  ModelCatalog,
} from '@/domain/models/agentProvider'
import {
  toAgentProvider,
  toAgentProviderVerification,
  toAgentProviders,
  toCreateProviderPayload,
  toModelCatalog,
  toUpdateProviderPayload,
  type AgentProviderDto,
  type AgentProviderListDto,
  type AgentProviderVerifyDto,
  type ModelCatalogDto,
} from '@/infrastructure/dto/agentProvider.dto'

import { request } from './client'

/** 契约路径（相对 API_BASE_URL=/api/v1） */
export const AGENT_PROVIDER_API_PATHS = {
  providers: '/agent/providers',
  provider: (providerId: string) =>
    `/agent/providers/${encodeURIComponent(providerId)}`,
  verify: (providerId: string) =>
    `/agent/providers/${encodeURIComponent(providerId)}/verify`,
  setDefault: (providerId: string) =>
    `/agent/providers/${encodeURIComponent(providerId)}/set-default`,
  modelCatalog: '/agent/model-catalog',
} as const

/** GET /agent/providers —— 我的供应商（Key 掩码 + 有效窗口/来源） */
export async function listAgentProviders(): Promise<AgentProvider[]> {
  const dto = await request<AgentProviderListDto>('GET', AGENT_PROVIDER_API_PATHS.providers)
  return toAgentProviders(dto)
}

/** POST /agent/providers —— 新建（Key 加密入库） */
export async function createAgentProvider(
  input: AgentProviderInput
): Promise<AgentProvider> {
  const dto = await request<AgentProviderDto>(
    'POST',
    AGENT_PROVIDER_API_PATHS.providers,
    toCreateProviderPayload(input)
  )
  return toAgentProvider(dto)
}

/** PUT /agent/providers/{id} —— 修改；api_key 留空 = 不变 */
export async function updateAgentProvider(
  providerId: string,
  input: AgentProviderInput
): Promise<AgentProvider> {
  const dto = await request<AgentProviderDto>(
    'PUT',
    AGENT_PROVIDER_API_PATHS.provider(providerId),
    toUpdateProviderPayload(input)
  )
  return toAgentProvider(dto)
}

/** DELETE /agent/providers/{id} —— 逻辑删除并清空密文 */
export async function deleteAgentProvider(providerId: string): Promise<void> {
  await request<{ id?: string; status?: string }>(
    'DELETE',
    AGENT_PROVIDER_API_PATHS.provider(providerId)
  )
}

/** POST /agent/providers/{id}/verify —— 轻量连通性验证（不回显 Key） */
export async function verifyAgentProvider(
  providerId: string
): Promise<AgentProviderVerification> {
  const dto = await request<AgentProviderVerifyDto>(
    'POST',
    AGENT_PROVIDER_API_PATHS.verify(providerId),
    undefined,
    { unwrapResponse: false }
  )
  return toAgentProviderVerification(dto)
}

/** POST /agent/providers/{id}/set-default —— 设为默认 */
export async function setDefaultAgentProvider(
  providerId: string
): Promise<AgentProvider> {
  const dto = await request<AgentProviderDto>(
    'POST',
    AGENT_PROVIDER_API_PATHS.setDefault(providerId)
  )
  return toAgentProvider(dto)
}

/** GET /agent/model-catalog —— 目录默认窗口 / 最大输出（表单预填） */
export async function fetchModelCatalog(): Promise<ModelCatalog> {
  const dto = await request<ModelCatalogDto>(
    'GET',
    AGENT_PROVIDER_API_PATHS.modelCatalog
  )
  return toModelCatalog(dto)
}
