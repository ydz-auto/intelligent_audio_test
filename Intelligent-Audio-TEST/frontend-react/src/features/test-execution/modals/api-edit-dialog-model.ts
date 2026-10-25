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
  return {
    method: typeof base.method === 'string' ? base.method : '',
    headers: rowsFromRecord(base.headers),
    bodyTemplateMode: typeof body === 'string' ? 'raw' : 'json',
    bodyTemplateText: valueToText(body),
    wsHeaders: rowsFromRecord(base.ws_headers),
    sessionConfig: valueToText(base.session_config),
    pacing: valueToText(base.pacing),
    vendorAdapter: typeof base.vendor_adapter === 'string' ? base.vendor_adapter : '',
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
  }

  const vendorAdapter = draft.vendorAdapter.trim()
  assignOrDelete(next, 'vendor_adapter', vendorAdapter || undefined)

  return { meta: next, errors }
}

/* ------------------------------------------------------------------ */
/* 响应解析页签（INT-1778，母卡 INT-1750 §2.3；写 meta）                 */
/* ------------------------------------------------------------------ */

/**
 * 响应解析页签声明的 8 个 meta 键（消费点 `api_driver_adapter.py:451-521,558`）。
 * 注意：C0（INT-1745）裁定这些解析器只在该算法类型**零输出字段声明**时逐键兜底，
 * 判定依据是同一次 GET /algorithm/params?param_type=api 没有 direction=output 行——
 * 该口径由页签顶部提示表达，代码侧不据此做门禁（`api_driver_adapter` 目前直接读 meta）。
 */
export const RESPONSE_PARSER_META_KEYS = [
  'result_parser',
  'asr_mapping',
  'trans_mapping',
  'sentence_end_mapping',
  'session_end_mapping',
  'error_code_mapping',
  'error_msg_mapping',
  'append_mode',
] as const

/** 后端取值缺省（`api_driver_adapter.py:506-512`）；只作输入框 placeholder，不预填、不写库 */
export const RESPONSE_PARSER_PATH_DEFAULTS = {
  asrMapping: 'asr_result',
  transMapping: 'translation_result',
  sentenceEndMapping: 'is_sentence_end',
  sessionEndMapping: 'session_finished',
  errorCodeMapping: 'code',
  errorMsgMapping: 'msg',
} as const

/** 三态：'' = 不写该键（沿用缺省），true/false = 显式写入 */
export type AppendModeValue = '' | 'true' | 'false'

export interface ResponseParserDraft {
  /** JSON 对象文本（asr_text_path / trans_text_path / session_id_path） */
  resultParser: string
  asrMapping: string
  transMapping: string
  sentenceEndMapping: string
  sessionEndMapping: string
  errorCodeMapping: string
  errorMsgMapping: string
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
    asrMapping: '',
    transMapping: '',
    sentenceEndMapping: '',
    sessionEndMapping: '',
    errorCodeMapping: '',
    errorMsgMapping: '',
    appendMode: '',
  }
}

function textOfPath(value: unknown): string {
  return typeof value === 'string' ? value : valueToText(value)
}

/** 编辑态回填：base meta → 响应解析草稿（append_mode 三态，缺省为空串） */
export function responseParserDraftFromMeta(
  meta: Record<string, unknown> | null | undefined
): ResponseParserDraft {
  const base = isPlainObject(meta) ? meta : {}
  return {
    resultParser: valueToText(base.result_parser),
    asrMapping: textOfPath(base.asr_mapping),
    transMapping: textOfPath(base.trans_mapping),
    sentenceEndMapping: textOfPath(base.sentence_end_mapping),
    sessionEndMapping: textOfPath(base.session_end_mapping),
    errorCodeMapping: textOfPath(base.error_code_mapping),
    errorMsgMapping: textOfPath(base.error_msg_mapping),
    appendMode:
      base.append_mode === true ? 'true' : base.append_mode === false ? 'false' : '',
  }
}

/**
 * 草稿 + base meta → 保存用的完整 meta 对象（与请求模板同一套 base 合并语义）：
 * - 只覆盖本页签声明的 8 个键，其余键（含请求模板页签的键）原样保留；
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

  const pathKeys = [
    ['asr_mapping', draft.asrMapping],
    ['trans_mapping', draft.transMapping],
    ['sentence_end_mapping', draft.sentenceEndMapping],
    ['session_end_mapping', draft.sessionEndMapping],
    ['error_code_mapping', draft.errorCodeMapping],
    ['error_msg_mapping', draft.errorMsgMapping],
  ] as const
  for (const [key, value] of pathKeys) {
    assignOrDelete(next, key, value.trim() || undefined)
  }

  assignOrDelete(
    next,
    'append_mode',
    draft.appendMode === '' ? undefined : draft.appendMode === 'true'
  )

  return { meta: next, errors }
}

/* ------------------------------------------------------------------ */
/* 端点行四项整数（优先级 / 最大进程 / 超时 / 音频时长） */
/* ------------------------------------------------------------------ */

/**
 * 端点行数值字段的合法区间（与旧实现的原生 min/max 完全一致）。
 * INT-1939 返工：表单加了 noValidate 后原生约束不再拦截，改由这里自查。
 */
export const ENDPOINT_NUMERIC_RULES = [
  { field: 'priority', label: '优先级', min: 1, max: 10 },
  { field: 'maxProcess', label: '最大进程', min: 1, max: 100 },
  { field: 'maxTimeout', label: '超时(s)', min: 1, max: 300 },
  { field: 'maxAudioDuration', label: '音频时长(s)', min: 1, max: null },
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
