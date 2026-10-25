/**
 * API 设备 meta 合并（INT-1621；INT-1800 起不再管理协议）。
 * 后端 api_crud_service 更新时按入参整块覆盖 meta（仅在入参未带 api_keys 时并回既有密钥池），
 * 抽屉表单只管理 environment 一个键，直接提交会把 version / 旧 apiKey 等
 * 表单未识别的键静默清空。编辑保存前用本函数把该设备原始 meta 的未识别键原样带回，
 * 只覆写表单管理的键；新建没有原始 meta，仍只写该键。
 *
 * 注意：`protocol` / `streaming` 是 `apis` 表列（INT-1800 / B0 §3.2），不再是 meta 键，
 * 本函数**不写也不清** meta.protocol——迁移脚本负责把存量键删掉。
 */
export interface ApiMetaFormValues {
  environment?: string | null
}

export function mergeApiDeviceMeta(
  currentMeta: Record<string, unknown> | null | undefined,
  form: ApiMetaFormValues
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...(currentMeta ?? {}) }
  // 表单未给出值时保留原值，避免「换个字段保存」把环境也一并抹掉
  const environment = form.environment?.trim()
  if (environment) merged.environment = environment
  return merged
}
