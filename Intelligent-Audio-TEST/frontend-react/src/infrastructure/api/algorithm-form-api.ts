/**
 * 算法参数表单 schema 真实 API（infrastructure/api 层；INT-710 批量设置专属参数接线）。
 * GET /algorithm/form-schema/{algo_type}（algorithm_bp.py:188；algorithm:read 门槛）。
 * 对照实测契约（voice_llm 2026-10-18）：data { algorithmType, algorithmName, description,
 * groups: [{ name, label, fields: [...] }], fields: [...] }；
 * 字段形态 { fieldCode, fieldName, fieldType, required, defaultValue, component,
 * helpText, hidden, uiOrder, scope }——component 取值 input/textarea/input-number/
 * select/slider/switch/code-editor（旧 Vue DynamicForm.vue 同源口径）。
 */
import { apiClient } from './client'

export interface AlgorithmFormField {
  code: string
  label: string
  /** 展示组件（input/textarea/input-number/select/slider/switch/code-editor） */
  component: string
  /** 值类型（text/number/switch/json/select 等） */
  type: string
  required: boolean
  defaultValue: unknown
  helpText: string | null
  hidden: boolean
  options?: string[]
  scope: string | null
}

export interface AlgorithmFormGroup {
  name: string
  label: string
  fields: AlgorithmFormField[]
}

export interface AlgorithmFormSchema {
  algorithmType: string
  algorithmName: string
  description: string | null
  groups: AlgorithmFormGroup[]
  /** 顶层未分组字段（部分算法 schema 无 groups，直接平铺 fields） */
  fields: AlgorithmFormField[]
}

interface AlgorithmFormSchemaDto {
  algorithmType?: string
  algorithmName?: string
  description?: string | null
  groups?: Array<{
    name?: string
    label?: string
    fields?: Array<Record<string, unknown>>
  }>
  fields?: Array<Record<string, unknown>>
}

function toFormField(raw: Record<string, unknown>): AlgorithmFormField {
  return {
    code: (raw.fieldCode as string) ?? '',
    label: (raw.fieldName as string) ?? (raw.fieldCode as string) ?? '',
    component: (raw.component as string) ?? 'input',
    type: (raw.fieldType as string) ?? 'text',
    required: Boolean(raw.required),
    defaultValue: raw.defaultValue,
    helpText: (raw.helpText as string | null) ?? null,
    hidden: Boolean(raw.hidden),
    options: Array.isArray(raw.options) ? (raw.options as string[]) : undefined,
    scope: (raw.scope as string | null) ?? null,
  }
}

/** 算法参数表单 schema（GET /algorithm/form-schema/{algo_type}） */
export async function fetchAlgorithmFormSchema(
  algoType: string
): Promise<AlgorithmFormSchema | null> {
  const dto = await apiClient.get<AlgorithmFormSchemaDto>(
    `/algorithm/form-schema/${algoType}`
  )
  if (!dto?.algorithmType) return null
  return {
    algorithmType: dto.algorithmType,
    algorithmName: dto.algorithmName ?? '',
    description: dto.description ?? null,
    groups: (dto.groups ?? []).map((g) => ({
      name: g.name ?? '',
      label: g.label ?? g.name ?? '',
      fields: (g.fields ?? []).map(toFormField),
    })),
    fields: (dto.fields ?? []).map(toFormField),
  }
}
