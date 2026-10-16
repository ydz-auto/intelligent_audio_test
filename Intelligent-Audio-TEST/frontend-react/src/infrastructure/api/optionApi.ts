/**
 * 系统选项 API 桩（infrastructure 层，红线④：mock 常量）。
 * 通道：KV 全量拉取 + 单键写入（对齐 newAPI `/api/option/` GET/PUT）。
 * TODO(API 接线): 本平台选项接口待建（INT-347 实施前置）——落定时仅替换本层：
 * GET /api/option/（全量 KV）、PUT /api/option/（单键 {key, value}）；REST 拆分
 * 按域时同样只改本层，interfaces/application 不感知。
 */
import type { SystemOptions } from '@/domain/models/option'
import {
  fetchSystemOptions,
  updateSystemOption,
} from '@/infrastructure/mock/settings-mock'

export const SYSTEM_OPTIONS_QUERY_KEY = ['system-options'] as const

export async function getSystemOptions(): Promise<SystemOptions> {
  return fetchSystemOptions()
}

export async function putSystemOption(
  key: string,
  value: unknown
): Promise<void> {
  await updateSystemOption(key, value)
}
