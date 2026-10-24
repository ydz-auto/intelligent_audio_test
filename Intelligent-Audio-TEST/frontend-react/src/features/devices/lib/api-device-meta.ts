/**
 * API 设备 meta 合并（INT-1621）。
 * 后端 api_crud_service 更新时按入参整块覆盖 meta（仅在入参未带 api_keys 时并回既有密钥池），
 * 而抽屉表单只管理 protocol / environment 两个键，直接提交会把 version / 旧 apiKey 等
 * 表单未识别的键静默清空。编辑保存前用本函数把该设备原始 meta 的未识别键原样带回，
 * 只覆写表单管理的两键；新建没有原始 meta，仍只写这两键。
 */
export interface ApiMetaFormValues {
  protocol: string
  environment?: string | null
}

export function mergeApiDeviceMeta(
  currentMeta: Record<string, unknown> | null | undefined,
  form: ApiMetaFormValues
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...(currentMeta ?? {}) }
  // 表单未给出值时保留原值，避免「换个字段保存」把协议/环境也一并抹掉
  const protocol = form.protocol?.trim()
  if (protocol) merged.protocol = protocol
  const environment = form.environment?.trim()
  if (environment) merged.environment = environment
  return merged
}
