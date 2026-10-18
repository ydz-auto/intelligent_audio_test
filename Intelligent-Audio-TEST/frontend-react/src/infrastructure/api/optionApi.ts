/**
 * 系统选项真实 API（infrastructure/api 层；接线 INT-651）。
 * 对照 INT-620 契约（api_gateway/routes/option_bp.py，根级挂载无 /api/v1 前缀）：
 * GET /api/option/（全量 KV，权限码 option:read）、PUT /api/option/（单键
 * { key, value }，权限码 option:write）；经 client.ts rootPath 走根级 base，
 * token 注入 / 统一信封解包与其余接口一致。
 * snake_case↔camelCase：本层无转换需求（KV 键即 `域.分区.字段`，值类型与
 * domain/models/option.ts SystemOptionValue 对齐），application/domain 不感知。
 */
import type { SystemOptions } from '@/domain/models/option'
import { apiClient } from '@/infrastructure/api/client'

export const SYSTEM_OPTIONS_QUERY_KEY = ['system-options'] as const

/** 全量选项拉取（GET /api/option/；信封解包后 data 即 KV Record） */
export async function getSystemOptions(): Promise<SystemOptions> {
  const data = await apiClient.get<SystemOptions>('/option/', { rootPath: true })
  return data ?? {}
}

/** 单键写入（PUT /api/option/ { key, value }；仅脏字段逐项调用） */
export async function putSystemOption(
  key: string,
  value: unknown
): Promise<void> {
  await apiClient.put('/option/', { key, value }, { rootPath: true })
}
