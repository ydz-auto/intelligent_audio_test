/**
 * API 编辑弹窗的草稿模型：请求模板 / 响应解析两个写 meta 的页签 + audio_config（INT-1777 / INT-1778，
 * 母卡 INT-1750 §2.2 / §2.3 / §3.1）。
 *
 * meta 保存语义 = 后端整块 replace（api_crud_service.py:474-486），所以前端必须：
 * 1) 打开弹窗以 GET /apis 返回的 api.meta 原对象为 base；
 * 2) 页签只覆盖自己声明的键；
 * 3) 保存提交整个合并后的对象；某键被清空 → 从 base 删除该键（不写 null）；
 * 4) 用户未触碰任何 meta 字段 → 调用方不发 meta 键（由 dialog 的 dirty 标记保证）。
 * 两个页签都改过时按「base → 请求模板 → 响应解析」顺序串行合并，互不覆盖对方声明的键。
 *
 * 显隐口径统一走 domain 的协议/流式性两维（INT-1800：不得用裸 apis.device_type / meta.protocol）。
 * audio_config 写顶层列（apis.audio_config），校验口径对齐 api_crud_service._validate_audio_config。
 */
/** 请求模板页签声明的 meta 键（HTTP 组 / WS 组 / 会话组；vendor_adapter 各组都显示） */
export const META_HTTP_KEYS = ['method', 'headers', 'body_template', 'vendor_adapter'] as const
export const META_WS_KEYS = ['ws_headers', 'session_config', 'pacing', 'vendor_adapter'] as const

/**
 * gRPC 组声明的 `meta.grpc` 子键（A3 / INT-1791 §4.1）。
 * 键集 = 后端 `grpc_adapter.py:48,79-100` 的读取侧（`_REQUIRED_CONFIG_KEYS` +
 * proto/proto_sha256/proto_size/metadata/deadline_ms），一个不多一个不少。
 */
export const META_GRPC_KEYS = [
  'proto_object_key',
  'proto_sha256',
  'proto_size',
  'service',
  'method',
  'method_kind',
  'metadata',
  'deadline_ms',
] as const

/** `meta.grpc.method_kind` 值域（`grpc_client` descriptor 必须与之一致，否则 GrpcMethodKindError） */
export const GRPC_METHOD_KINDS = ['unary', 'server_stream', 'bidi'] as const
export type GrpcMethodKind = (typeof GRPC_METHOD_KINDS)[number]

export function isGrpcMethodKind(value: unknown): value is GrpcMethodKind {
  return typeof value === 'string' && (GRPC_METHOD_KINDS as readonly string[]).includes(value)
}

/**
 * 鉴权类 metadata 键（§4.1）：值用密码控件输入。
 * **当前明文存储 / 回显**（后端 `_api_to_dict` 只脱敏 `meta.api_keys`），脱敏归 INT-1953。
 */
export const GRPC_METADATA_SECRET_KEYS = ['authorization', 'x-api-key', 'api-key'] as const

/** proto 文件大小上限（`shared` 的 PROTO_MAX_BYTES = 256 KiB，读写两侧同口径） */
export const PROTO_MAX_BYTES = 256 * 1024

/**
 * SSE 组声明的 `meta.sse` 子键（A3 / INT-1791 §4.2 = 01 契约 §11.2 权威键表）。
 * 后端 `api_crud_service._SSE_CONFIG_KEYS` 同集，**未知键一律 400**。
 */
export const META_SSE_KEYS = [
  'event_name_field',
  'params',
  'reconnect_enabled',
  'max_reconnect_attempts',
  'retry_ms',
  'idle_timeout_ms',
  'max_duration_ms',
] as const

/** SSE 数值键的值域（`sse_policy.py` 常量；前端镜像，不自行放宽） */
export const SSE_FIELD_LIMITS = {
  retryMs: { min: 0, max: 60000 },
  idleTimeoutMs: { min: 1, max: 3600000 },
  maxDurationMs: { min: 1, max: 3600000 },
  maxReconnectAttempts: { min: 0, max: 10 },
} as const

/** SSE 缺省值（只作 placeholder / 展示，不预填、不写库；后端执行侧同值） */
export const SSE_DEFAULTS = {
  eventNameField: 'event',
  retryMs: 1000,
  maxReconnectAttempts: 2,
} as const

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
  /* ---- WS 流式的两段载荷（Qwen live-translate 这类方言） ---- */
  /** 首帧载荷（meta.first_frame，建连后一次；占位符取自 session_config） */
  firstFrameEnabled: boolean
  firstFrameTemplate: string
  /** 音频帧载荷（meta.audio_frame；占位符 {{audio_b64}} / {{event_id}}） */
  audioFrameEnabled: boolean
  audioFrameTemplate: string
  /* ---- gRPC 组（meta.grpc；A3 §4.1） ---- */
  grpcProtoObjectKey: string
  grpcProtoSha256: string
  grpcProtoSize: string
  grpcService: string
  grpcMethod: string
  grpcMethodKind: string
  grpcMetadata: KeyValueRow[]
  grpcDeadlineMs: string
  /* ---- SSE 组（meta.sse；A3 §4.2；method / headers 复用上面的 HTTP 组草稿） ---- */
  sseEventNameField: string
  sseParams: KeyValueRow[]
  sseReconnectEnabled: boolean
  sseMaxReconnectAttempts: string
  sseRetryMs: string
  sseIdleTimeoutMs: string
  sseMaxDurationMs: string
}

/** 保存前拦截的字段级错误（field 为页签内控件名，dialog 据此定位输入框） */
export interface MetaDraftError {
  field:
    | 'method'
    | 'headers'
    | 'bodyTemplate'
    | 'wsHeaders'
    | 'sessionConfig'
    | 'pacing'
    | 'firstFrameTemplate'
    | 'audioFrameTemplate'
    | 'grpcProto'
    | 'grpcService'
    | 'grpcMethod'
    | 'grpcMethodKind'
    | 'grpcMetadata'
    | 'grpcDeadlineMs'
    | 'sseEventNameField'
    | 'sseParams'
    | 'sseReconnect'
    | 'sseMaxReconnectAttempts'
    | 'sseRetryMs'
    | 'sseIdleTimeoutMs'
    | 'sseMaxDurationMs'
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
    firstFrameEnabled: false,
    firstFrameTemplate: '',
    audioFrameEnabled: false,
    audioFrameTemplate: '',
    grpcProtoObjectKey: '',
    grpcProtoSha256: '',
    grpcProtoSize: '',
    grpcService: '',
    grpcMethod: '',
    grpcMethodKind: '',
    grpcMetadata: [],
    grpcDeadlineMs: '',
    sseEventNameField: '',
    sseParams: [],
    sseReconnectEnabled: false,
    sseMaxReconnectAttempts: '',
    sseRetryMs: '',
    sseIdleTimeoutMs: '',
    sseMaxDurationMs: '',
  }
}

/** 编辑态回填：base meta → 页签草稿（body_template 字符串 = 原始模板模式，对象 = 结构化 JSON 模式） */
export function requestTemplateDraftFromMeta(
  meta: Record<string, unknown> | null | undefined
): RequestTemplateDraft {
  const base = isPlainObject(meta) ? meta : {}
  const body = base.body_template
  // meta.grpc / meta.sse 是嵌套对象（A3 §二.3）：子键逐键回填，缺省留空不预填
  const grpc = isPlainObject(base.grpc) ? base.grpc : {}
  const sse = isPlainObject(base.sse) ? base.sse : {}
  const firstFrame = isPlainObject(base.first_frame) ? base.first_frame : {}
  const audioFrame = isPlainObject(base.audio_frame) ? base.audio_frame : {}
  return {
    method: typeof base.method === 'string' ? base.method : '',
    headers: rowsFromRecord(base.headers),
    bodyTemplateMode: typeof body === 'string' ? 'raw' : 'json',
    bodyTemplateText: valueToText(body),
    wsHeaders: rowsFromRecord(base.ws_headers),
    sessionConfig: valueToText(base.session_config),
    pacing: valueToText(base.pacing),
    vendorAdapter: typeof base.vendor_adapter === 'string' ? base.vendor_adapter : '',
    firstFrameEnabled: firstFrame.enabled === true,
    firstFrameTemplate: valueToText(firstFrame.template),
    audioFrameEnabled: audioFrame.enabled === true,
    audioFrameTemplate: valueToText(audioFrame.template),
    grpcProtoObjectKey: valueToText(grpc.proto_object_key),
    grpcProtoSha256: valueToText(grpc.proto_sha256),
    grpcProtoSize: valueToText(grpc.proto_size),
    grpcService: valueToText(grpc.service),
    grpcMethod: valueToText(grpc.method),
    grpcMethodKind: valueToText(grpc.method_kind),
    grpcMetadata: rowsFromRecord(grpc.metadata),
    grpcDeadlineMs: valueToText(grpc.deadline_ms),
    sseEventNameField: valueToText(sse.event_name_field),
    sseParams: rowsFromRecord(sse.params),
    sseReconnectEnabled: sse.reconnect_enabled === true,
    sseMaxReconnectAttempts: valueToText(sse.max_reconnect_attempts),
    sseRetryMs: valueToText(sse.retry_ms),
    sseIdleTimeoutMs: valueToText(sse.idle_timeout_ms),
    sseMaxDurationMs: valueToText(sse.max_duration_ms),
  }
}

/**
 * 写一段「开关 + JSON 模板」的载荷配置（meta.first_frame / meta.audio_frame）。
 *
 * 后端契约：`{"enabled": true, "template": {...}}`；关闭时删键，回落执行侧默认
 * （首帧 = session.update，音频帧 = input_audio_buffer.append）。
 */
function mergeFrameTemplate(
  next: Record<string, unknown>,
  key: 'first_frame' | 'audio_frame',
  enabled: boolean,
  text: string,
  label: string,
  field: 'firstFrameTemplate' | 'audioFrameTemplate',
  errors: MetaDraftError[]
): void {
  if (!enabled) {
    assignOrDelete(next, key, undefined)
    return
  }
  if (!text.trim()) {
    errors.push({ field, message: `${label}不能为空（关闭开关即回落默认载荷）` })
    return
  }
  const template = parseJsonObject(text, label, field, errors)
  if (!template) return
  next[key] = { enabled: true, template }
}

/**
 * 从请求模板 / 响应解析推导字段（INT-1778 后的自动口径）：
 *
 * - 输入字段 = `body_template` 里出现的 `{{占位符}}`（下发时由渲染器替换）；
 * - 输出字段 = `result_parser` 声明的 asr_text_path / trans_text_path / session_id_path。
 *
 * 用途：参数配置页签在用户没手工声明时也能看到「这套配置会用到/产出哪些字段」，
 * 避免出现「没有地方配置输入字段」的死角。
 */
export interface DerivedFields {
  /** 请求模板占位符（去重、保持出现顺序） */
  input: string[]
  /** 响应解析声明的输出字段（code 为字段名，path 为响应路径） */
  output: Array<{ code: string; path: string }>
}

const RESULT_PARSER_OUTPUT_KEYS: Array<{ key: string; code: string }> = [
  { key: 'asr_text_path', code: 'asr_text' },
  { key: 'trans_text_path', code: 'trans_text' },
  { key: 'session_id_path', code: 'session_id' },
]

function collectPlaceholders(value: unknown, out: string[]): void {
  if (typeof value === 'string') {
    for (const match of value.matchAll(/\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}/g)) {
      if (!out.includes(match[1])) out.push(match[1])
    }
    return
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectPlaceholders(item, out))
    return
  }
  if (value && typeof value === 'object') {
    Object.values(value as Record<string, unknown>).forEach((item) =>
      collectPlaceholders(item, out)
    )
  }
}

export function deriveFieldsFromMeta(
  meta: Record<string, unknown> | null | undefined
): DerivedFields {
  const base = isPlainObject(meta) ? meta : {}
  const input: string[] = []
  collectPlaceholders(base.body_template, input)
  collectPlaceholders(base.body, input)

  const parser = isPlainObject(base.result_parser) ? base.result_parser : {}
  const output = RESULT_PARSER_OUTPUT_KEYS.map(({ key, code }) => ({
    code,
    path: valueToText(parser[key]),
  })).filter((row) => row.path.trim() !== '')

  return { input, output }
}

/**
 * WS 两段载荷的示例提示（Qwen live-translate 方言，实测自 `第三方/qwen_api`）：
 * 首帧 = session.update，音频帧 = input_audio_buffer.append。
 */
export const FIRST_FRAME_HINT = `{
  "event_id": "event_{{timestamp_ms}}",
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "translation": { "language": "en" }
  }
}`

export const AUDIO_FRAME_HINT = `{
  "event_id": "event_{{timestamp_ms}}",
  "type": "input_audio_buffer.append",
  "audio": "{{audio_b64}}"
}`

/**
 * 请求模板页签的显隐与合并（INT-1800 / B0 §3.5：协议决定请求配置区，流式性决定轮次/会话配置区）：
 * - `protocol === 'websocket'` → WS 请求头；
 * - `protocol === 'http'` → 请求方法 / 请求头 / 请求体模板；
 * - `streaming === true` → 会话配置 / 节奏控制（轮次与会话语义）。
 * 两组键互不覆盖，未触碰的键原样留在 base 里。
 */
export interface RequestTemplateTarget {
  protocol: string | null
  streaming: boolean
}

function parseJsonObject<F extends string>(
  text: string,
  label: string,
  field: F,
  errors: Array<{ field: F; message: string }>
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
 * 子对象级合并（A3 §二.3 / 本卡最大技术风险点）：
 * 后端 `meta` 整块 replace（`api_crud_service.py:531-543`），`meta.grpc` / `meta.sse`
 * 是嵌套对象 —— 以读侧 base 的同名子对象为底，**只覆盖本组声明的子键**，
 * 清空即删该子键，子对象清空则删整个键；绝不整块重建，
 * 否则切协议 / 换页签会把别的键（含未声明的子键）冲掉。
 */
function mergeNestedObject(
  target: Record<string, unknown>,
  key: string,
  entries: Record<string, unknown | undefined>
): void {
  const baseSub = isPlainObject(target[key])
    ? { ...(target[key] as Record<string, unknown>) }
    : {}
  for (const [subKey, value] of Object.entries(entries)) {
    if (value === undefined) delete baseSub[subKey]
    else baseSub[subKey] = value
  }
  if (Object.keys(baseSub).length === 0) delete target[key]
  else target[key] = baseSub
}

/** 整数输入（空 = 不写该键）；越界 / 非整数 → 字段级错误 */
function parseIntegerField(
  text: string,
  label: string,
  field: MetaDraftError['field'],
  limits: { min: number; max: number },
  errors: MetaDraftError[]
): number | undefined {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  if (!/^\d+$/.test(trimmed)) {
    errors.push({ field, message: `${label}必须为整数` })
    return undefined
  }
  const value = Number(trimmed)
  if (value < limits.min || value > limits.max) {
    errors.push({ field, message: `${label}必须在 ${limits.min}-${limits.max} 之间` })
    return undefined
  }
  return value
}

/**
 * gRPC metadata 键值表 → 对象（镜像 `grpc_client` 的 `validate_metadata`）：
 * 键必须小写、值不含 CR/LF、支持 `{{placeholder}}`（值不校验占位符）。
 */
function grpcMetadataToRecord(
  rows: ReadonlyArray<KeyValueRow>,
  errors: MetaDraftError[]
): Record<string, string> {
  const record: Record<string, string> = {}
  for (const row of rows) {
    const key = row.key.trim()
    if (!key && !row.value.trim()) continue
    if (!key) {
      errors.push({ field: 'grpcMetadata', message: 'metadata 名称不能为空' })
      continue
    }
    if (key !== key.toLowerCase()) {
      errors.push({ field: 'grpcMetadata', message: `metadata 名称必须为小写：${key}` })
      continue
    }
    if (key in record) {
      errors.push({ field: 'grpcMetadata', message: `metadata 名称重复：${key}` })
      continue
    }
    if (/[\r\n]/.test(row.value)) {
      errors.push({ field: 'grpcMetadata', message: `metadata 值不能包含换行：${key}` })
      continue
    }
    record[key] = row.value
  }
  return record
}

/** gRPC 组：必填 / method_kind / deadline / metadata 校验 + `meta.grpc` 子对象合并 */
function mergeGrpcGroup(
  next: Record<string, unknown>,
  draft: RequestTemplateDraft,
  errors: MetaDraftError[]
): void {
  const objectKey = draft.grpcProtoObjectKey.trim()
  const sha = draft.grpcProtoSha256.trim().toLowerCase()
  const sizeText = draft.grpcProtoSize.trim()
  const service = draft.grpcService.trim()
  const method = draft.grpcMethod.trim()
  const methodKind = draft.grpcMethodKind.trim()

  // 必填（后端 grpc_config：proto_object_key + service/method/method_kind，
  // 缺失在执行期才报 GrpcProtoError；前端提交前按同一口径拦截）
  if (!objectKey) {
    errors.push({
      field: 'grpcProto',
      message: '缺少 proto 文件引用（proto_object_key）：上传 .proto 后自动填入',
    })
  }
  if (sha && !/^[0-9a-f]{64}$/.test(sha)) {
    errors.push({ field: 'grpcProto', message: 'proto_sha256 必须为 64 位小写十六进制' })
  }
  let protoSize: number | undefined
  if (sizeText) {
    if (!/^\d+$/.test(sizeText)) {
      errors.push({ field: 'grpcProto', message: 'proto_size 必须为整数' })
    } else if (Number(sizeText) > PROTO_MAX_BYTES) {
      errors.push({
        field: 'grpcProto',
        message: `proto 文件超过 ${PROTO_MAX_BYTES} 字节上限`,
      })
    } else {
      protoSize = Number(sizeText)
    }
  }
  if (!service) {
    errors.push({ field: 'grpcService', message: '请填写或选择 service' })
  }
  if (!method) {
    errors.push({ field: 'grpcMethod', message: '请填写或选择 method' })
  }
  if (!methodKind) {
    errors.push({ field: 'grpcMethodKind', message: '请选择 method_kind' })
  } else if (!isGrpcMethodKind(methodKind)) {
    errors.push({
      field: 'grpcMethodKind',
      message: `method_kind 非法：${methodKind}（合法值：unary / server_stream / bidi）`,
    })
  }
  // deadline_ms：正整数（后端 `grpc_adapter.deadline_ms` 要求 > 0，没有上限）
  const deadlineText = draft.grpcDeadlineMs.trim()
  let deadlineMs: number | undefined
  if (deadlineText) {
    if (!/^\d+$/.test(deadlineText)) {
      errors.push({ field: 'grpcDeadlineMs', message: 'deadline_ms（毫秒）必须为正整数' })
    } else if (Number(deadlineText) <= 0) {
      errors.push({ field: 'grpcDeadlineMs', message: 'deadline_ms（毫秒）必须为正数' })
    } else {
      deadlineMs = Number(deadlineText)
    }
  }
  const metadata = grpcMetadataToRecord(draft.grpcMetadata, errors)

  mergeNestedObject(next, 'grpc', {
    proto_object_key: objectKey || undefined,
    proto_sha256: sha || undefined,
    proto_size: protoSize,
    service: service || undefined,
    method: method || undefined,
    method_kind: methodKind || undefined,
    metadata: Object.keys(metadata).length ? metadata : undefined,
    deadline_ms: deadlineMs,
  })
}

/** SSE 组：`meta.method` / `meta.headers`（所有权在 HTTP 组）+ `meta.sse` 子对象 */
function mergeSseGroup(
  next: Record<string, unknown>,
  draft: RequestTemplateDraft,
  errors: MetaDraftError[]
): void {
  // SSE 复用 HTTP 组的 method / headers（缺省 GET / 空）；不写 body_template ——
  // A2 执行侧 `_render_request_body` 在 protocol == 'sse' 时直接返回 meta.sse.params，
  // 从不读 body_template，写了也是死键（§4.2）。
  assignOrDelete(next, 'method', draft.method.trim() || undefined)
  const headers = rowsToRecord(draft.headers, '请求头', 'headers', errors)
  assignOrDelete(next, 'headers', Object.keys(headers).length ? headers : undefined)

  const eventNameField = draft.sseEventNameField.trim()
  if (draft.sseEventNameField && !eventNameField) {
    errors.push({
      field: 'sseEventNameField',
      message: '事件名字段必须为非空字符串（留空 = 使用缺省 event）',
    })
  }
  const params = rowsToRecord(draft.sseParams, 'SSE 请求参数', 'sseParams', errors)
  const retryMs = parseIntegerField(
    draft.sseRetryMs,
    '重连退避上限（retry_ms）',
    'sseRetryMs',
    SSE_FIELD_LIMITS.retryMs,
    errors
  )
  const idleTimeoutMs = parseIntegerField(
    draft.sseIdleTimeoutMs,
    '空闲超时（idle_timeout_ms）',
    'sseIdleTimeoutMs',
    SSE_FIELD_LIMITS.idleTimeoutMs,
    errors
  )
  const maxDurationMs = parseIntegerField(
    draft.sseMaxDurationMs,
    '整体时长上限（max_duration_ms）',
    'sseMaxDurationMs',
    SSE_FIELD_LIMITS.maxDurationMs,
    errors
  )
  const maxReconnectAttempts = parseIntegerField(
    draft.sseMaxReconnectAttempts,
    '重连次数上限（max_reconnect_attempts）',
    'sseMaxReconnectAttempts',
    SSE_FIELD_LIMITS.maxReconnectAttempts,
    errors
  )

  mergeNestedObject(next, 'sse', {
    event_name_field: eventNameField || undefined,
    params: Object.keys(params).length ? params : undefined,
    reconnect_enabled: draft.sseReconnectEnabled,
    max_reconnect_attempts: maxReconnectAttempts,
    retry_ms: retryMs,
    idle_timeout_ms: idleTimeoutMs,
    max_duration_ms: maxDurationMs,
  })
}

/**
 * 草稿 + base meta → 保存用的完整 meta 对象。
 * - 只覆盖当前协议/流式性那几组声明的键（隐藏组的旧键原样保留在 base 里，不删）；
 * - `meta.grpc` / `meta.sse` 走子对象级合并（见 mergeNestedObject），不整块重建；
 * - 字段清空 → 删除该键（不写 null）；
 * - 非法 JSON / 空键名 / 键名重复 / 必填缺失 / 越界 → 返回 errors，调用方拦截保存、弹窗不关。
 */
export function mergeRequestTemplateMeta(
  baseMeta: Record<string, unknown> | null | undefined,
  draft: RequestTemplateDraft,
  target: RequestTemplateTarget
): { meta: Record<string, unknown>; errors: MetaDraftError[] } {
  const next: Record<string, unknown> = isPlainObject(baseMeta) ? { ...baseMeta } : {}
  const errors: MetaDraftError[] = []

  if (target.protocol === 'websocket') {
    const wsHeaders = rowsToRecord(draft.wsHeaders, 'WS 请求头', 'wsHeaders', errors)
    assignOrDelete(next, 'ws_headers', Object.keys(wsHeaders).length ? wsHeaders : undefined)
  } else if (target.protocol === 'http') {
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
  } else if (target.protocol === 'grpc') {
    mergeGrpcGroup(next, draft, errors)
  } else if (target.protocol === 'sse') {
    mergeSseGroup(next, draft, errors)
  }

  // 轮次 / 会话配置区由流式性决定，且只有 HTTP / WS 两条执行道读这组键
  // （SSE 的请求载荷只有 meta.sse.params，gRPC 走 metadata，见 §4.1 / §4.2）
  if (
    target.streaming &&
    (target.protocol === 'websocket' || target.protocol === 'http')
  ) {
    assignOrDelete(
      next,
      'session_config',
      parseJsonObject(draft.sessionConfig, '会话配置', 'sessionConfig', errors)
    )
    assignOrDelete(next, 'pacing', parseJsonObject(draft.pacing, '节奏控制', 'pacing', errors))
    // WS 流式的两段载荷（Qwen live-translate 这类方言）：首帧一次、音频帧每 100ms
    if (target.protocol === 'websocket') {
      mergeFrameTemplate(
        next,
        'first_frame',
        draft.firstFrameEnabled,
        draft.firstFrameTemplate,
        '首帧载荷',
        'firstFrameTemplate',
        errors
      )
      mergeFrameTemplate(
        next,
        'audio_frame',
        draft.audioFrameEnabled,
        draft.audioFrameTemplate,
        '音频帧载荷',
        'audioFrameTemplate',
        errors
      )
    }
  }

  const vendorAdapter = draft.vendorAdapter.trim()
  assignOrDelete(next, 'vendor_adapter', vendorAdapter || undefined)

  return { meta: next, errors }
}

/* ------------------------------------------------------------------ */
/* 响应解析页签（INT-1778，母卡 INT-1750 §2.3；写 meta）                 */
/* ------------------------------------------------------------------ */

/**
 * 响应解析页签写入的 meta 键（消费点 `api_driver_adapter.py:451-521,558`）。
 * 注意：C0（INT-1745）裁定这些解析器只在该算法类型**零输出字段声明**时逐键兜底，
 * 判定依据是同一次 GET /algorithm/params?param_type=api 没有 direction=output 行——
 * 该口径由页签顶部提示表达，代码侧不据此做门禁（`api_driver_adapter` 目前直接读 meta）。
 *
 * 负责人 2026-10-31 裁定：6 个 `*_mapping`（asr / trans / 句结束 / 会话结束 /
 * 错误码 / 错误信息）属于后端内置缺省即可的专家参数，不在 UI 暴露；
 * 存量 meta 里已有的这些键**原样保留**，不读、不写、不删。
 */
export const RESPONSE_PARSER_META_KEYS = ['result_parser', 'append_mode'] as const

/** 三态：'' = 不写该键（沿用缺省），true/false = 显式写入 */
export type AppendModeValue = '' | 'true' | 'false'

export interface ResponseParserDraft {
  /** JSON 对象文本（asr_text_path / trans_text_path / session_id_path） */
  resultParser: string
  appendMode: AppendModeValue
}

/** 响应解析页签保存前拦截的字段级错误 */
export interface ResponseParserDraftError {
  field: 'resultParser'
  message: string
}

export function emptyResponseParserDraft(): ResponseParserDraft {
  return {
    resultParser: '',
    appendMode: '',
  }
}

/** 编辑态回填：base meta → 响应解析草稿（append_mode 三态，缺省为空串） */
export function responseParserDraftFromMeta(
  meta: Record<string, unknown> | null | undefined
): ResponseParserDraft {
  const base = isPlainObject(meta) ? meta : {}
  return {
    resultParser: valueToText(base.result_parser),
    appendMode:
      base.append_mode === true ? 'true' : base.append_mode === false ? 'false' : '',
  }
}

/**
 * 草稿 + base meta → 保存用的完整 meta 对象（与请求模板同一套 base 合并语义）：
 * - 只覆盖本页签声明的键，其余键（含请求模板页签的键、存量 `*_mapping`）原样保留；
 * - 输入清空 → 删除该键（后端回落到内置缺省，不写 null / 空串）；
 * - `result_parser` 非法 JSON / 非对象 → 返回 errors，调用方拦截保存。
 */
export function mergeResponseParserMeta(
  baseMeta: Record<string, unknown> | null | undefined,
  draft: ResponseParserDraft
): { meta: Record<string, unknown>; errors: ResponseParserDraftError[] } {
  const next: Record<string, unknown> = isPlainObject(baseMeta) ? { ...baseMeta } : {}
  const errors: ResponseParserDraftError[] = []

  assignOrDelete(
    next,
    'result_parser',
    parseJsonObject(draft.resultParser, '响应解析器', 'resultParser', errors)
  )

  assignOrDelete(
    next,
    'append_mode',
    draft.appendMode === '' ? undefined : draft.appendMode === 'true'
  )

  return { meta: next, errors }
}

/* ------------------------------------------------------------------ */
/* 端点行四项整数（优先级 / 端点最大并发 / 超时 / 音频时长） */
/* ------------------------------------------------------------------ */

/**
 * 端点行数值字段的合法区间（与旧实现的原生 min/max 完全一致）。
 * INT-1939 返工：表单加了 noValidate 后原生约束不再拦截，改由这里自查。
 *
 * 命名口径：`maxProcess` 是**单个端点**的并发上限（端点级），与 API 级
 * `default_max_process`（所有端点合计的总并发）区分，避免两个“最大并发”混淆。
 */
export const ENDPOINT_NUMERIC_RULES = [
  { field: 'priority', label: '优先级', ariaLabel: '端点优先级', min: 1, max: 10 },
  {
    field: 'maxProcess',
    label: '端点最大并发',
    ariaLabel: '端点最大并发',
    min: 1,
    max: 100,
  },
  { field: 'maxTimeout', label: '超时(s)', ariaLabel: '端点超时(s)', min: 1, max: 300 },
  {
    field: 'maxAudioDuration',
    label: '音频时长(s)',
    ariaLabel: '端点音频时长(s)',
    min: 1,
    max: null,
  },
] as const

export type EndpointNumericField = (typeof ENDPOINT_NUMERIC_RULES)[number]['field']
export type EndpointNumericErrors = Partial<Record<EndpointNumericField, string>>
export type EndpointNumericDraft = Record<EndpointNumericField, string>

function endpointRangeMessage(min: number, max: number | null): string {
  return max == null ? `请输入 ≥${min} 的整数` : `请输入 ${min}~${max} 的整数`
}

/**
 * 端点行四项整数的字段级校验（整数 + 区间，口径同原原生 min/max）。
 * 空串不报错：保存时按 `Number(v) || 缺省` 兜底，与改动前行为一致。
 */
export function validateEndpointNumbers(row: EndpointNumericDraft): EndpointNumericErrors {
  const errors: EndpointNumericErrors = {}
  for (const rule of ENDPOINT_NUMERIC_RULES) {
    const raw = row[rule.field].trim()
    if (raw === '') continue
    const value = Number(raw)
    if (!Number.isInteger(value) || value < rule.min || (rule.max != null && value > rule.max)) {
      errors[rule.field] = endpointRangeMessage(rule.min, rule.max)
    }
  }
  return errors
}

/* ------------------------------------------------------------------ */
/* audio_config（顶层列 apis.audio_config；输入 / 输出两套格式，INT-1771） */
/* ------------------------------------------------------------------ */

export const AUDIO_SAMPLE_RATE_OPTIONS = [8000, 16000, 24000, 48000] as const
export const AUDIO_BIT_DEPTH_OPTIONS = ['s16', 's24', 's32'] as const
export const AUDIO_CHANNEL_OPTIONS = [1, 2] as const
export const AUDIO_CONTAINER_OPTIONS = ['pcm', 'wav'] as const

/** 后端兼容 16/24/32 别名（api_crud_service._validate_audio_config → AudioBitDepth） */
const BIT_DEPTH_ALIASES: Record<string, string> = { '16': 's16', '24': 's24', '32': 's32' }

/** 一套音频格式可编辑的四项（输入侧 / 输出侧共用同一词表） */
const AUDIO_FORMAT_KEYS = ['sample_rate', 'bit_depth', 'channels', 'container'] as const
/** 不随分向拆分的附加键：保存时原样保留，并复制进两侧子对象（执行侧只读子对象） */
const AUDIO_SHARED_KEYS = ['format', 'chunk_duration_ms'] as const

export interface AudioFormatDraft {
  sampleRate: string
  bitDepth: string
  channels: string
  container: string
}

/**
 * 输入 / 输出两套格式：下发给被测服务的（input）与回传的（output）可以不同。
 * 落库形态 `{input: {...}, output: {...}}`，与后端 `resolve_audio_config(direction)` 同口径。
 */
export interface AudioConfigDraft {
  input: AudioFormatDraft
  output: AudioFormatDraft
}

/** 分向展示文案（顺序即 UI 顺序；两套控件同一词表） */
export const AUDIO_DIRECTION_FIELDS = [
  {
    key: 'input',
    label: '输入音频格式（下发给被测服务）',
    hint: '混音渲染的目标格式；未配置回退 24000Hz / s16 / 单声道 / pcm',
  },
  {
    key: 'output',
    label: '输出音频格式（被测服务回传）',
    hint: '回传音频的采样率口径；未配置回退输入侧同值',
  },
] as const

export type AudioDirection = (typeof AUDIO_DIRECTION_FIELDS)[number]['key']

export function emptyAudioFormatDraft(): AudioFormatDraft {
  return { sampleRate: '', bitDepth: '', channels: '', container: '' }
}

function audioFormatDraftFrom(raw: unknown): AudioFormatDraft {
  const base = isPlainObject(raw) ? raw : {}
  const bitDepth = valueToText(base.bit_depth)
  return {
    sampleRate: valueToText(base.sample_rate),
    bitDepth: BIT_DEPTH_ALIASES[bitDepth] ?? bitDepth,
    channels: valueToText(base.channels),
    container: valueToText(base.container),
  }
}

export function emptyAudioConfigDraft(): AudioConfigDraft {
  return { input: emptyAudioFormatDraft(), output: emptyAudioFormatDraft() }
}

/**
 * 编辑态回填：分向对象优先；存量扁平配置（输入输出共用）→ 两侧同值。
 * 只配了单侧时另一侧按后端回退语义取同值，避免展示与执行口径分叉。
 */
export function audioConfigDraftFrom(
  raw: Record<string, unknown> | null | undefined
): AudioConfigDraft {
  const base = isPlainObject(raw) ? raw : {}
  const flat = audioFormatDraftFrom(base)
  const sideOf = (key: AudioDirection): AudioFormatDraft | null =>
    isPlainObject(base[key]) ? audioFormatDraftFrom(base[key]) : null
  const inputSide = sideOf('input')
  const outputSide = sideOf('output')
  const input = inputSide ?? outputSide ?? flat
  const output = outputSide ?? inputSide ?? flat
  // 两侧必须是独立副本，否则改一侧会连带改另一侧
  return { input: { ...input }, output: { ...output } }
}

function audioSideToObject(side: AudioFormatDraft): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (side.sampleRate) out.sample_rate = Number(side.sampleRate)
  if (side.bitDepth) out.bit_depth = side.bitDepth
  if (side.channels) out.channels = Number(side.channels)
  if (side.container) out.container = side.container
  return out
}

/**
 * 草稿 + base audio_config → 保存用对象。
 * - 扁平四项（旧形态）一律删除，改写成 `input` / `output` 两个子对象；
 * - base 的 `format` / `chunk_duration_ms` 原样保留并复制进两侧（执行侧只读子对象）；
 * - 某侧四项全空 → 删除该侧（目标侧回退另一侧同值）；两侧全空 → 返回 {}
 *   （显式清除音频格式的写入口径）。
 */
export function buildAudioConfig(
  base: Record<string, unknown> | null | undefined,
  draft: AudioConfigDraft
): Record<string, unknown> {
  const next: Record<string, unknown> = isPlainObject(base) ? { ...base } : {}
  for (const key of AUDIO_FORMAT_KEYS) delete next[key]
  const shared: Record<string, unknown> = {}
  for (const key of AUDIO_SHARED_KEYS) {
    if (key in next) shared[key] = next[key]
  }
  for (const { key } of AUDIO_DIRECTION_FIELDS) {
    const side = audioSideToObject(draft[key])
    if (Object.keys(side).length === 0) {
      delete next[key]
      continue
    }
    next[key] = { ...shared, ...side }
  }
  return next
}
