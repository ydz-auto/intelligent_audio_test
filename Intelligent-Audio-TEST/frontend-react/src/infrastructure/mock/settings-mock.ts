/**
 * 系统选项 mock 数据源（infrastructure 层，红线④：mock 常量）。
 * 形态对照 newAPI `/api/option/` KV 通道；本平台选项接口待建（实施前置），
 * 后续 REST 拆分仅替换 api 层读写，interfaces/application 不感知。
 */
import { SYSTEM_OPTION_DEFAULTS, type SystemOptions } from '@/domain/models/option'

/** mock：当前系统选项 KV（默认值基线；接线前为可视稿常数） */
export const MOCK_SYSTEM_OPTIONS: SystemOptions = {
  ...SYSTEM_OPTION_DEFAULTS,
  'site.name': '智能语音测试平台',
  'site.logo': '',
  'site.footer': '© 2026 智能语音测试平台',
  'site.notice': '',
}

/** 读取全量选项（KV 通道；TODO(API 接线): GET /api/option/ 或按域 REST） */
export async function fetchSystemOptions(): Promise<SystemOptions> {
  return MOCK_SYSTEM_OPTIONS
}

/** 写入单键（仅脏字段逐项 PUT；TODO(API 接线): PUT /api/option/ {key, value}） */
export async function updateSystemOption(
  key: string,
  value: unknown
): Promise<{ key: string; value: unknown }> {
  MOCK_SYSTEM_OPTIONS[key] = value as SystemOptions[keyof SystemOptions]
  return { key, value }
}
