/**
 * 被测 API 的「协议 × 流式性」两维（INT-2025，对齐后端 INT-1799 / INT-1800 契约）
 *
 * - `protocol`：传输协议，规范值 http / websocket / sse / grpc（`apis.protocol` 列，只存规范值）；
 * - `streaming`：交互形态，true = 流式（实时）/ false = 非流式（非实时，`apis.streaming` 列）；
 * - 两维正交：执行道只由 `streaming` 派生，协议不参与。
 *
 * 后端 `device_type` 已废弃：写侧携带非空值一律 400
 * （"device_type 已废弃，请改用 protocol + streaming"）。
 *
 * 可用组合矩阵与后端 `shared/models/common_enums.py AVAILABLE_PROTOCOL_STREAMING` 同表，
 * 前端置灰/锁定只允许这张表内的形态，避免提交后端必拒的组合。
 */

/** 协议规范值（顺序 = 下拉展示顺序） */
export const API_PROTOCOLS = ['http', 'websocket', 'sse', 'grpc'] as const

export type ApiProtocol = (typeof API_PROTOCOLS)[number]

/** 新建表单预选值（= 后端写侧缺省值） */
export const DEFAULT_API_PROTOCOL: ApiProtocol = 'http'
export const DEFAULT_API_STREAMING = false

/** 协议展示名（下拉与列表徽章同口径） */
export const API_PROTOCOL_LABEL: Record<ApiProtocol, string> = {
  http: 'HTTP',
  websocket: 'WebSocket',
  sse: 'SSE',
  grpc: 'gRPC',
}

/** 已实现执行器的「协议 × 流式性」组合（与后端 AVAILABLE_PROTOCOL_STREAMING 同一张表） */
const WRITABLE_COMBINATIONS: ReadonlyArray<{ protocol: ApiProtocol; streaming: boolean }> = [
  { protocol: 'http', streaming: false },
  { protocol: 'http', streaming: true },
  { protocol: 'websocket', streaming: true },
  { protocol: 'sse', streaming: true },
  { protocol: 'grpc', streaming: false },
  { protocol: 'grpc', streaming: true },
]

export function isApiProtocol(value: unknown): value is ApiProtocol {
  return typeof value === 'string' && (API_PROTOCOLS as readonly string[]).includes(value)
}

/** 协议下拉选项（含展示名；未上线协议 disabled 置灰） */
export function apiProtocolOptions(): Array<{ value: ApiProtocol; label: string; disabled: boolean }> {
  return API_PROTOCOLS.map((protocol) => ({
    value: protocol,
    label: API_PROTOCOL_LABEL[protocol],
    disabled: !WRITABLE_COMBINATIONS.some((combo) => combo.protocol === protocol),
  }))
}

/** 切换协议时的流式性缺省值（websocket / sse 天然流式；http / grpc 缺省非流式） */
export function defaultStreamingFor(protocol: unknown): boolean {
  return protocol === 'websocket' || protocol === 'sse'
}

/**
 * 该协议的流式开关是否锁定：协议只有一种可写流式性时锁定
 * （websocket / sse 只有流式一条；http / grpc 两条都可写 → 不锁）。
 */
export function isStreamingLocked(protocol: unknown): boolean {
  if (!isApiProtocol(protocol)) return true
  const writable = new Set(
    WRITABLE_COMBINATIONS.filter((combo) => combo.protocol === protocol).map((combo) => combo.streaming)
  )
  return writable.size <= 1
}

/** 流式性展示文案 */
export function streamingLabel(streaming: boolean): string {
  return streaming ? '流式' : '非流式'
}
