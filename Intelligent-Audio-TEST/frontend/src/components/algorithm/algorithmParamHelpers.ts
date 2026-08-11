import { algorithmApi } from '../../utils/api'

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

export function normalizeParamFields(param: any) {
  return {
    ...param,
    param_code: param.paramCode ?? param.param_code,
    param_name: param.paramName ?? param.param_name,
    param_type: param.paramType ?? param.param_type,
    ui_group: param.uiGroup ?? param.ui_group,
    ui_order: param.uiOrder ?? param.ui_order,
    default_value: param.defaultValue ?? param.default_value,
    required: param.required,
    hidden: param.hidden,
    direction: param.direction,
    label: param.label,
    help_text: param.helpText ?? param.help_text
  }
}

export function normalizeCaseParamFields(param: any) {
  const normalized = {
    ...param,
    param_code: param.paramCode ?? param.param_code,
    param_name: param.paramName ?? param.param_name,
    param_type: param.paramType ?? param.param_type,
    label: param.label,
    required: param.required,
    default_value: param.defaultValue ?? param.default_value,
    help_text: param.helpText ?? param.help_text,
    ui_order: param.uiOrder ?? param.ui_order,
    hidden: param.hidden,
    scope: param.scope ?? 'common',
    min_value: param.minValue ?? param.min_value ?? param.min ?? null,
    max_value: param.maxValue ?? param.max_value ?? param.max ?? null,
    step: param.step ?? null,
    unit: param.unit ?? '',
    annotation_code: param.annotationCode ?? param.annotation_code ?? null,
    field_path: param.fieldPath ?? param.field_path ?? null
  }
  // 确保 component 字段与 param_type 同步
  if (!normalized.component) {
    normalized.component = getDefaultComponent(normalized.param_type || 'text')
  }
  return normalized
}

export function buildReferenceParamData(p: any) {
  return {
    code: p.code,
    name: p.name,
    type: p.type,
    annotation_code: p.annotation_code || p.code,
    annotation_format: p.annotation_format || null,
    field_path: p.field_path || null,
    merge_mode: p.merge_mode || 'join',
    help_text: p.help_text
  }
}
