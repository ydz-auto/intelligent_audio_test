/**
 * API 编辑弹窗「请求模板」页签与 audio_config 的草稿模型（INT-1777，母卡 INT-1750 §2.2 / §3.1）。
 *
 * meta 保存语义 = 后端整块 replace（api_crud_service.py:474-486），所以前端必须：
 * 1) 打开弹窗以 GET /apis 返回的 api.meta 原对象为 base；
 * 2) 页签只覆盖自己声明的键；
 * 3) 保存提交整个合并后的对象；某键被清空 → 从 base 删除该键（不写 null）；
 * 4) 用户未触碰任何 meta 字段 → 调用方不发 meta 键（由 dialog 的 dirty 标记保证）。
 *
 * 设备类型显隐统一走 domain 的 deriveApiTargetDeviceType（不得用裸 apis.device_type / meta.protocol）。
 * audio_config 写顶层列（apis.audio_config），校验口径对齐 api_crud_service._validate_audio_config。
 */
import type { DeviceType } from '@/domain/models/device'
import { deriveApiTargetDeviceType } from '@/domain/models/apiConfig'

/** 请求模板页签声明的 meta 键（HTTP 组 / WS 组；vendor_adapter 两组都显示） */
export const META_HTTP_KEYS = ['method', 'headers', 'body_template', 'vendor_adapter'] as const
export const META_WS_KEYS = ['ws_headers', 'session_config', 'pacing', 'vendor_adapter'] as const

export const HTTP_METHOD_OPTIONS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const

export interface KeyValueRow {
  id: string
  key: string
  value: string
}

export type BodyTemplateMode = 'json' | 'raw'

export interface RequestTemplateDraft {
  method: string
  headers: KeyValueRow[]
  bodyTemplateMode: BodyTemplateMode
  bodyTemplateText: string
  wsHeaders: KeyValueRow[]
  sessionConfig: string
  pacing: string
  vendorAdapter: string
}

/** 保存前拦截的字段级错误（field 为页签内控件名，dialog 据此定位输入框） */
export interface MetaDraftError {
  field: 'method' | 'headers' | 'bodyTemplate' | 'wsHeaders' | 'sessionConfig' | 'pacing'
  message: string
}

let kvSeq = 0

export function newKeyValueRow(key = '', value = ''): KeyValueRow {
  kvSeq += 1
  return { id: `kv-${kvSeq}`, key, value }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function valueToText(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return prettyJson(value)
}

function rowsFromRecord(value: unknown): KeyValueRow[] {
  if (!isPlainObject(value)) return []
  return Object.entries(value).map(([key, raw]) => newKeyValueRow(key, valueToText(raw)))
}

export function emptyRequestTemplateDraft(): RequestTemplateDraft {
  return {
    method: '',
    headers: [],
    bodyTemplateMode: 'json',
    bodyTemplateText: '',
    wsHeaders: [],
    sessionConfig: '',
    pacing: '',
    vendorAdapter: '',
  }
}

/** 编辑态回填：base meta → 页签草稿（body_template 字符串 = 原始模板模式，对象 = 结构化 JSON 模式） */
export function requestTemplateDraftFromMeta(
  meta: Record<string, unknown> | null | undefined
): RequestTemplateDraft {
  const base = isPlainObject(meta) ? meta : {}
  const body = base.body_template
  return {
    method: typeof base.method === 'string' ? base.method : '',
    headers: rowsFromRecord(base.headers),
    bodyTemplateMode: typeof body === 'string' ? 'raw' : 'json',
    bodyTemplateText: valueToText(body),
    wsHeaders: rowsFromRecord(base.ws_headers),
    sessionConfig: valueToText(base.session_config),
    pacing: valueToText(base.pacing),
    vendorAdapter: typeof base.vendor_adapter === 'string' ? base.vendor_adapter : '',
  }
}

/**
 * 新增态 / 端点草稿派生目标设备类型：直接复用 deriveApiTargetDeviceType
 * （显式 deviceType 优先，auto 时按首个非空端点协议派生，无端点缺省 http_api）。
 */
export function deriveDraftTargetDeviceType(
  deviceType: 'auto' | 'http_api' | 'websocket_api',
  endpoints: ReadonlyArray<{ endpoint: string }>
): DeviceType {
  return deriveApiTargetDeviceType({
    deviceType: deviceType === 'auto' ? null : deviceType,
    endpoints,
  })
}

function parseJsonObject(
  text: string,
  label: string,
  field: MetaDraftError['field'],
  errors: MetaDraftError[]
): Record<string, unknown> | undefined {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  try {
    const parsed = JSON.parse(trimmed) as unknown
    if (!isPlainObject(parsed)) {
      errors.push({ field, message: `${label}必须是 JSON 对象` })
      return undefined
    }
    return parsed
  } catch {
    errors.push({ field, message: `${label} JSON 格式不正确` })
    return undefined
  }
}

function rowsToRecord(
  rows: ReadonlyArray<KeyValueRow>,
  label: string,
  field: MetaDraftError['field'],
  errors: MetaDraftError[]
): Record<string, string> {
  const record: Record<string, string> = {}
  for (const row of rows) {
    const key = row.key.trim()
    if (!key && !row.value.trim()) continue
    if (!key) {
      errors.push({ field, message: `${label}名称不能为空` })
      continue
    }
    if (key in record) {
      errors.push({ field, message: `${label}名称重复：${key}` })
      continue
    }
    record[key] = row.value
  }
  return record
}

function assignOrDelete(
  target: Record<string, unknown>,
  key: string,
  value: unknown
): void {
  if (value === undefined) {
    delete target[key]
    return
  }
  target[key] = value
}

/**
 * 草稿 + base meta → 保存用的完整 meta 对象。
 * - 只覆盖当前设备类型那组声明的键（隐藏组的旧键原样保留在 base 里，不删）；
 * - 字段清空 → 删除该键（不写 null）；
 * - 非法 JSON / 空键名 / 键名重复 → 返回 errors，调用方拦截保存、弹窗不关。
 */
export function mergeRequestTemplateMeta(
  baseMeta: Record<string, unknown> | null | undefined,
  draft: RequestTemplateDraft,
  targetDeviceType: DeviceType
): { meta: Record<string, unknown>; errors: MetaDraftError[] } {
  const next: Record<string, unknown> = isPlainObject(baseMeta) ? { ...baseMeta } : {}
  const errors: MetaDraftError[] = []

  if (targetDeviceType === 'websocket_api') {
    const wsHeaders = rowsToRecord(draft.wsHeaders, 'WS 请求头', 'wsHeaders', errors)
    assignOrDelete(next, 'ws_headers', Object.keys(wsHeaders).length ? wsHeaders : undefined)
    assignOrDelete(
      next,
      'session_config',
      parseJsonObject(draft.sessionConfig, '会话配置', 'sessionConfig', errors)
    )
    assignOrDelete(next, 'pacing', parseJsonObject(draft.pacing, '节奏控制', 'pacing', errors))
  } else {
    const method = draft.method.trim()
    assignOrDelete(next, 'method', method || undefined)
    const headers = rowsToRecord(draft.headers, '请求头', 'headers', errors)
    assignOrDelete(next, 'headers', Object.keys(headers).length ? headers : undefined)
    if (draft.bodyTemplateMode === 'raw') {
      assignOrDelete(next, 'body_template', draft.bodyTemplateText.trim() || undefined)
    } else {
      assignOrDelete(
        next,
        'body_template',
        parseJsonObject(draft.bodyTemplateText, '请求体模板', 'bodyTemplate', errors)
      )
    }
  }

  const vendorAdapter = draft.vendorAdapter.trim()
  assignOrDelete(next, 'vendor_adapter', vendorAdapter || undefined)

  return { meta: next, errors }
}

/* ------------------------------------------------------------------ */
/* audio_config（顶层列 apis.audio_config，四项 = 采样率/位深/通道数/容器） */
/* ------------------------------------------------------------------ */

export const AUDIO_SAMPLE_RATE_OPTIONS = [8000, 16000, 24000, 48000] as const
export const AUDIO_BIT_DEPTH_OPTIONS = ['s16', 's24', 's32'] as const
export const AUDIO_CHANNEL_OPTIONS = [1, 2] as const
export const AUDIO_CONTAINER_OPTIONS = ['pcm', 'wav'] as const

/** 后端兼容 16/24/32 别名（api_crud_service._validate_audio_config → AudioBitDepth） */
const BIT_DEPTH_ALIASES: Record<string, string> = { '16': 's16', '24': 's24', '32': 's32' }

export interface AudioConfigDraft {
  sampleRate: string
  bitDepth: string
  channels: string
  container: string
}

export function emptyAudioConfigDraft(): AudioConfigDraft {
  return { sampleRate: '', bitDepth: '', channels: '', container: '' }
}

export function audioConfigDraftFrom(
  raw: Record<string, unknown> | null | undefined
): AudioConfigDraft {
  const base = isPlainObject(raw) ? raw : {}
  const bitDepth = valueToText(base.bit_depth)
  return {
    sampleRate: valueToText(base.sample_rate),
    bitDepth: BIT_DEPTH_ALIASES[bitDepth] ?? bitDepth,
    channels: valueToText(base.channels),
    container: valueToText(base.container),
  }
}

/**
 * 草稿 + base audio_config → 保存用对象。
 * 保留 base 里本页签不编辑的已知键（format / chunk_duration_ms），本四项清空则删除该键；
 * 全部为空时返回 {}（显式清除音频格式的写入口径）。
 */
export function buildAudioConfig(
  base: Record<string, unknown> | null | undefined,
  draft: AudioConfigDraft
): Record<string, unknown> {
  const next: Record<string, unknown> = isPlainObject(base) ? { ...base } : {}
  const assign = (key: string, raw: string, convert: (v: string) => unknown) => {
    if (raw === '') {
      delete next[key]
      return
    }
    next[key] = convert(raw)
  }
  assign('sample_rate', draft.sampleRate, Number)
  assign('bit_depth', draft.bitDepth, (v) => v)
  assign('channels', draft.channels, Number)
  assign('container', draft.container, (v) => v)
  return next
}
