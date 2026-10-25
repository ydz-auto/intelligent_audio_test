/**
 * 被测 API 的「协议 × 流式性」两维（INT-1800 / B0《09_API协议面与执行道契约》）。
 *
 * - `protocol`：传输协议，值域 4 值（http / websocket / sse / grpc），只存规范值；
 * - `streaming`：交互形态，true = 流式（= 实时），false = 非流式（= 非实时）；
 * - 两者**独立**：协议不参与执行道判断，执行道（lane）只由 streaming 派生。
 *
 * 可用矩阵（A3 / INT-1791：与后端 `AVAILABLE_PROTOCOL_STREAMING` 同一张表）：
 *   http + 非流式 / http + 流式（chunked） / websocket + 流式 / sse + 流式 /
 *   grpc + 非流式（unary） / grpc + 流式（server-stream / bidi） → 已上线
 *   其余 2 种组合                                             → 后端 400「组合实现未上线」，前端置灰并提示
 *
 * 前端不自行推断协议：协议只读 `apis.protocol` 列，流式性只读 `apis.streaming` 列，
 * 不读 `meta.protocol`、不按端点前缀派生（§3.4 裁定五「单一来源」）。
 */

/** 协议规范值域（后端 `APIProtocol` 枚举同值域；一句话里不再出现 https/ws/wss） */
export const API_PROTOCOLS = ['http', 'websocket', 'sse', 'grpc'] as const

export type ApiProtocol = (typeof API_PROTOCOLS)[number]

/** 新建表单预选值（= 后端写侧缺省值，§3.2.1） */
export const DEFAULT_API_PROTOCOL: ApiProtocol = 'http'
export const DEFAULT_API_STREAMING = false

/** 协议展示名（列表徽章 / 表单下拉同口径） */
export const API_PROTOCOL_LABEL: Record<ApiProtocol, string> = {
  http: 'HTTP',
  websocket: 'WebSocket',
  sse: 'SSE',
  grpc: 'gRPC',
}

/** 流式性展示文案（两维中的第二维） */
export function streamingLabel(streaming: boolean): string {
  return streaming ? '流式' : '非流式'
}

export interface ApiProtocolCombination {
  protocol: ApiProtocol
  streaming: boolean
}

/**
 * 当前批次**可写**的组合（B0 §3.2.3 可用矩阵）。
 *
 * A3（INT-1791）按后端 `shared/models/common_enums.py AVAILABLE_PROTOCOL_STREAMING`
 * 扩成同一张表（A1 gRPC 两条 + A2 `sse+true` / `http+true`），**不多不少**：
 * 前端放行后端必拒的组合 = 踩「前端不得自行放宽」红线，反之亦然。
 * 前端与后端各自独立校验：前端置灰 + 提示，后端写侧显式 400。
 */
const WRITABLE_COMBINATIONS: readonly ApiProtocolCombination[] = [
  { protocol: 'http', streaming: false },
  { protocol: 'websocket', streaming: true },
  { protocol: 'grpc', streaming: false },
  { protocol: 'grpc', streaming: true },
  { protocol: 'sse', streaming: true },
  { protocol: 'http', streaming: true },
]

export function isApiProtocol(value: unknown): value is ApiProtocol {
  return typeof value === 'string' && (API_PROTOCOLS as readonly string[]).includes(value)
}

/** 该协议是否至少有一种可用组合（A1 / A2 上线后 4 个协议均为 true） */
export function isProtocolImplemented(protocol: string | null | undefined): boolean {
  if (!isApiProtocol(protocol)) return false
  return WRITABLE_COMBINATIONS.some((combo) => combo.protocol === protocol)
}

/** 该「协议 × 流式性」组合当前是否可保存（后端写侧同一矩阵） */
export function isCombinationImplemented(
  protocol: string | null | undefined,
  streaming: boolean
): boolean {
  if (!isApiProtocol(protocol)) return false
  return WRITABLE_COMBINATIONS.some(
    (combo) => combo.protocol === protocol && combo.streaming === streaming
  )
}

/** 切换协议时的流式性缺省值（websocket / sse 天然流式，http / grpc unary 非流式） */
export function defaultStreamingFor(protocol: string | null | undefined): boolean {
  return protocol === 'websocket' || protocol === 'sse'
}

/**
 * 该协议的流式开关是否被锁定：该协议只有一种可写流式性时锁定，
 * 避免用户组合出后端必拒的形态（websocket / sse 只有流式一条，
 * http / grpc 两条都有 → 解锁）。
 */
export function isStreamingLocked(protocol: string | null | undefined): boolean {
  if (!isApiProtocol(protocol)) return true
  const writable = new Set(
    WRITABLE_COMBINATIONS.filter((combo) => combo.protocol === protocol).map(
      (combo) => combo.streaming
    )
  )
  return writable.size <= 1
}

/** 组合不可用时的提示文案（与后端 400 文案同口径，§3.2.3 第 2 条） */
export function unavailableCombinationReason(
  protocol: string | null | undefined,
  streaming: boolean
): string | null {
  if (isCombinationImplemented(protocol, streaming)) return null
  if (!isApiProtocol(protocol)) return '协议取值非法'
  if (!isProtocolImplemented(protocol)) return '协议实现未上线'
  return `协议 ${protocol} 与流式性 streaming=${streaming} 的组合实现未上线`
}

/**
 * 执行亲和域令牌派生（B0 §3.3 唯一派生规则）：流式 → `websocket_api`（需实例亲和），
 * 非流式 → `http_api`（无状态）。只用于建任务 `case_devices[].device_type`，
 * 与协议无关（SSE 流式同样是亲和域）。
 */
export function deriveAffinityDeviceType(streaming: boolean): 'websocket_api' | 'http_api' {
  return streaming ? 'websocket_api' : 'http_api'
}

/** 表单下拉选项（含未上线项，供置灰渲染） */
export function apiProtocolOptions(): ReadonlyArray<{
  value: ApiProtocol
  label: string
  disabled: boolean
}> {
  return API_PROTOCOLS.map((protocol) => ({
    value: protocol,
    label: API_PROTOCOL_LABEL[protocol],
    disabled: !isProtocolImplemented(protocol),
  }))
}
