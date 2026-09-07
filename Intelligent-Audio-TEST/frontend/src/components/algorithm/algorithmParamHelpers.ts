export function getDefaultComponent(paramType: string): string {
  const typeComponentMap: Record<string, string> = {
    'text': 'input',
    'number': 'input-number',
    'textarea': 'textarea',
    'slider': 'slider',
    'switch': 'switch',
    'audio_select': 'audio-select',
    'device_select': 'device-select',
    'json': 'json-editor'
  }
  return typeComponentMap[paramType] || 'input'
}

/** 归一化参数字段为 camelCase Domain 形状（algorithmPort 已返回 camelCase，此处仅做形状收敛） */
export function normalizeParamFields(param: any) {
  return {
    ...param,
    paramCode: param.paramCode ?? '',
    paramName: param.paramName ?? '',
    paramType: param.paramType ?? 'text',
    uiGroup: param.uiGroup ?? '',
    uiOrder: param.uiOrder ?? 0,
    defaultValue: param.defaultValue,
    required: param.required,
    hidden: param.hidden,
    direction: param.direction,
    label: param.label,
    helpText: param.helpText ?? '',
  }
}

/** 归一化用例参数字段为 camelCase Domain 形状 */
export function normalizeCaseParamFields(param: any) {
  const normalized = {
    ...param,
    paramCode: param.paramCode ?? '',
    paramName: param.paramName ?? '',
    paramType: param.paramType ?? 'text',
    label: param.label,
    required: param.required,
    defaultValue: param.defaultValue,
    helpText: param.helpText ?? '',
    uiOrder: param.uiOrder ?? 0,
    hidden: param.hidden,
    scope: param.scope ?? 'common',
    minValue: param.minValue ?? param.min ?? null,
    maxValue: param.maxValue ?? param.max ?? null,
    step: param.step ?? null,
    unit: param.unit ?? '',
    annotationCode: param.annotationCode ?? null,
    fieldPath: param.fieldPath ?? null,
  }
  // 确保 component 字段与 paramType 同步
  if (!normalized.component) {
    normalized.component = getDefaultComponent(normalized.paramType || 'text')
  }
  return normalized
}

/** 构建参考参数请求体（camelCase Domain → snake_case 提交给后端） */
export function buildReferenceParamData(p: any) {
  return {
    code: p.code,
    name: p.name,
    type: p.type,
    annotationCode: p.annotationCode || p.code,
    annotationFormat: p.annotationFormat || null,
    fieldPath: p.fieldPath || null,
    mergeMode: p.mergeMode || 'join',
    helpText: p.helpText,
  }
}
