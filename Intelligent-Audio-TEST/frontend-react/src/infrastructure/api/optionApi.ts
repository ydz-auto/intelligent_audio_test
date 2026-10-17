/**
 * 系统选项 API 桩（infrastructure 层）。
 * 通道：KV 全量拉取 + 单键写入（对齐 newAPI `/api/option/` GET/PUT）。
 * TODO(API 接线, INT-620 done + client.ts 根路径): 端点契约已落（INT-620 done，
 * 2026-10-18 审计通过）：根级挂载**无 /api/v1 前缀**，GET /api/option/（全量 KV）、
 * PUT /api/option/（单键 {key, value}）。两重阻塞：① 本机常驻栈 2026-10-18 01:05
 * 实测 /api/option/ 仍 404（INT-620 分支未合入运行栈）；② client.ts baseURL 恒
 * /api/v1 无法直达根路径——需基座 client.ts 支持根路径（INT-641 子卡已派）。
 * 可用后仅替换本层；REST 拆分按域时同样只改本层，interfaces/application 不感知。
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
