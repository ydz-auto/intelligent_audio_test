/**
 * 参数映射视图公共纯函数 / 词表（Presentation 共用；无 React 依赖）。
 *
 * 抽自 mappings-section：参数选项构造、名称解析、评估来源词表、
 * 设备分组键（用例参数 scope / 参考参数 / 未分组）、判重键。
 */
import { toast } from 'sonner'

import type { CaseParamScope } from '@/domain/models/algorithmConfig'
import type { ParamOption } from './primitives'

/** 评估来源选项（V9.7.10 MappingEditor sourceOptions；后端 VALID_SOURCES 含 case_config） */
export const EVALUATION_SOURCE_OPTIONS = [
  { value: 'case', label: '用例参数' },
  { value: 'case_config', label: '用例配置' },
  { value: 'reference', label: '参考参数' },
  { value: 'device', label: '设备输出' },
] as const

/** 用例配置(config.rounds)可映射结构性字段：评估时从 test_case.config.rounds 按轮读取（V9.7.10 同款） */
export const CASE_CONFIG_FIELD_PRESETS = [{ code: 'audios', name: '被播放音频' }] as const

/** 源参数选项（设备共用：用例参数 + 参考参数；评估按 source 取对应集合） */
export function buildSourceOptions(
  caseParams: Array<{ paramCode: string; paramName?: string }>,
  referenceParams: Array<{ code: string; name?: string }>
): ParamOption[] {
  return [
    ...caseParams.map((param) => ({
      value: param.paramCode,
      label: `${param.paramCode} · ${param.paramName || '（未填名称）'}`,
    })),
    ...referenceParams.map((param) => ({
      value: param.code,
      label: `${param.code} · ${param.name || '（未填名称）'}`,
    })),
  ].filter((option) => option.value)
}

/** 按 code 取参数名（caseParams / deviceParams 走 paramCode/paramName；referenceParams 走 code/name） */
export function paramNameByCode(
  list: Array<{ paramCode?: string; paramName?: string; code?: string; name?: string }>,
  code: string
): string {
  if (!code) return ''
  const item = list.find((p) => (p.paramCode ?? p.code) === code)
  return item?.paramName ?? item?.name ?? ''
}

/** 评估源参数名称（按 source 取对应集合；V9.7.10 getParamName 口径） */
export function evalSourceParamName(
  source: string,
  code: string,
  caseParams: Array<{ paramCode: string; paramName?: string }>,
  referenceParams: Array<{ code: string; name?: string }>,
  deviceParams: Array<{ paramCode: string; paramName?: string }>
): string {
  if (!code) return ''
  switch (source) {
    case 'case_config':
      return CASE_CONFIG_FIELD_PRESETS.find((p) => p.code === code)?.name || ''
    case 'reference':
      return paramNameByCode(referenceParams, code)
    case 'device':
      return paramNameByCode(deviceParams, code)
    case 'case':
    default:
      return paramNameByCode(caseParams, code)
  }
}

/** 评估来源参数选项（按 source 取集合；V9.7.10 getSourceParams） */
export function evalSourceOptions(
  source: string,
  caseParams: Array<{ paramCode: string; paramName?: string }>,
  referenceParams: Array<{ code: string; name?: string }>,
  deviceParams: Array<{ paramCode: string; paramName?: string }>
): ParamOption[] {
  const toOptions = (list: Array<{ paramCode?: string; paramName?: string; code?: string; name?: string }>) =>
    list
      .map((param) => {
        const code = param.paramCode ?? param.code ?? ''
        return {
          value: code,
          label: `${code} · ${param.paramName || param.name || '（未填名称）'}`,
        }
      })
      .filter((option) => option.value)

  switch (source) {
    case 'case_config':
      return CASE_CONFIG_FIELD_PRESETS.map((p) => ({ value: p.code, label: p.name }))
    case 'reference':
      return toOptions(referenceParams)
    case 'device':
      return toOptions(deviceParams)
    case 'case':
    default:
      return toOptions(caseParams)
  }
}

/* ───────────────────────── 设备分组 ───────────────────────── */

/**
 * 设备分组键：源参数所属集合（用例参数·scope / 参考参数 / 未分组）。
 * 用例参数分组词表对齐后端 `CaseParamScope`（common + DeviceType 三值）。
 */
export type DeviceApiGroupKey =
  | 'case-common'
  | 'case-physical'
  | 'case-http_api'
  | 'case-websocket_api'
  | 'reference'
  | 'unknown'

/** 用例参数 scope → 分组键（唯一映射表，禁止散落相等判断） */
const CASE_SCOPE_GROUP_KEY: Record<CaseParamScope, DeviceApiGroupKey> = {
  common: 'case-common',
  physical: 'case-physical',
  http_api: 'case-http_api',
  websocket_api: 'case-websocket_api',
}

export const DEVICE_API_GROUP_ORDER: DeviceApiGroupKey[] = [
  'case-common',
  'case-physical',
  'case-http_api',
  'case-websocket_api',
  'reference',
  'unknown',
]

export const DEVICE_API_GROUP_LABEL: Record<DeviceApiGroupKey, string> = {
  'case-common': '用例参数 · 通用',
  'case-physical': '用例参数 · 真机',
  'case-http_api': '用例参数 · HTTP API',
  'case-websocket_api': '用例参数 · Realtime WS',
  reference: '参考参数',
  unknown: '未分组',
}

export function deviceApiGroupKey(
  sourceParam: string,
  caseParams: Array<{ paramCode: string; scope?: string }>,
  referenceParams: Array<{ code: string }>
): DeviceApiGroupKey {
  if (!sourceParam) return 'unknown'
  const caseParam = caseParams.find((p) => p.paramCode === sourceParam)
  if (caseParam) {
    // 后端已废弃旧词表（api/e2e），未知值按「通用」归组而不是丢弃
    return CASE_SCOPE_GROUP_KEY[caseParam.scope as CaseParamScope] ?? 'case-common'
  }
  if (referenceParams.some((p) => p.code === sourceParam)) return 'reference'
  return 'unknown'
}

/* ───────────────────────── 评估维度分组 ───────────────────────── */

/** 评估分组键：dimensionId（空归「未指定维度」；兼容存量按维度名兜底） */
export function evalGroupKey(row: { dimensionId?: string | null; dimensionName?: string | null }): string {
  if (row.dimensionId) return String(row.dimensionId)
  return row.dimensionName ? `name:${row.dimensionName}` : '__none__'
}

export function evalGroupName(
  key: string,
  dimensions: Array<{ id: number; name: string }>,
  dimensionNameById: Map<string, string>
): string {
  if (key === '__none__') return '未指定维度'
  if (key.startsWith('name:')) return key.slice(5)
  const dim = dimensions.find((d) => String(d.id) === key)
  return dim?.name || dimensionNameById.get(key) || `维度(${key})`
}

/* ───────────────────────── 判重（V9.7.10 唯一约束对齐） ───────────────────────── */

/** 判重键：评估 = (source, sourceParam, dimensionId)；设备 = (节类型, sourceParam) */
export function findDuplicateIndex(
  rows: Array<{ source?: string; sourceParam: string; dimensionId?: string }>,
  index: number,
  section: 'device' | 'evaluation'
): number {
  const current = rows[index]
  if (!current) return -1
  const src = section === 'evaluation' ? current.source || 'case' : section
  if (!src || !current.sourceParam) return -1
  const dimKey = current.dimensionId || ''
  for (let i = 0; i < rows.length; i++) {
    if (i === index) continue
    const other = rows[i]
    const otherSrc = section === 'evaluation' ? other.source || 'case' : section
    if (otherSrc !== src) continue
    if (other.sourceParam !== current.sourceParam) continue
    if ((other.dimensionId || '') !== dimKey) continue
    return i
  }
  return -1
}

export function warnDuplicate(sourceLabel: string, sourceParam: string, dimensionLabel: string) {
  toast.warning(
    `映射已存在：来源=${sourceLabel}，源参数=${sourceParam}${dimensionLabel ? `，维度=${dimensionLabel}` : ''}，同一来源+源参数+维度不允许重复`
  )
}
