/**
 * 系统选项 API（infrastructure 层，INT-729 接线）。
 * 契约对照 api_gateway/routes/option_bp.py（INT-620 实测）：
 * 根级挂载 GET/PUT /api/option/（无 /api/v1 前缀，权限码 option:read/write）——
 * GET 全量 KV（领域默认基线 ∪ 库中已存覆盖）、PUT {key, value} 单键写入。
 * 返回 SystemOptions 类型化解析由 application 层 resolve* 函数完成（option.ts）。
 */
import { apiClient } from './client'
import type { ApiRequestOptions } from './client'
import type { SystemOptions } from '@/domain/models/option'
import type { SystemOptionsDto } from '@/infrastructure/dto/iam.dto'

export const SYSTEM_OPTIONS_QUERY_KEY = ['system-options'] as const

/** 根级挂载端点（无 /api/v1 前缀） */
const OPTION_BASE_OPTIONS: ApiRequestOptions = { baseURL: '/api' }

export async function getSystemOptions(): Promise<SystemOptions> {
  const dto = await apiClient.get<SystemOptionsDto>('/option/', OPTION_BASE_OPTIONS)
  const options: SystemOptions = {}
  for (const [key, value] of Object.entries(dto ?? {})) {
    if (value !== null && value !== undefined) {
      options[key] = value as SystemOptions[keyof SystemOptions]
    }
  }
  return options
}

export async function putSystemOption(
  key: string,
  value: unknown
): Promise<void> {
  await apiClient.put('/option/', { key, value }, OPTION_BASE_OPTIONS)
}
