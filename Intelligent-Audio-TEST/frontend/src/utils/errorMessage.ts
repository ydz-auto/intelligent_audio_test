// -*- coding: utf-8 -*-
/**
 * 错误消息安全化 —— 防止原始 gRPC/RPC 异常文本直出页面 / Toast（INT-899，INT-858 N1）
 *
 * 后端 api_gateway 在算法/评估等 gRPC 服务异常时，会把原始异常透传进响应
 * message/detail（如 `<_InactiveRpcError of RPC that terminated with:
 * status=StatusCode.UNAVAILABLE details="failed to connect...">`）。
 * 直接渲染 error.message 会把整段多行内部异常文本暴露给用户。
 *
 * 统一在此收敛：
 * - toUserErrorMessage：识别原始 RPC 异常文本 → 返回固定友好文案（fallback）；
 *   正常业务错误 → 原样返回（单行化 + 截断，防多行/超长破坏布局）。
 * - toUserErrorDetail：仅当为原始 RPC 异常时返回完整原文，供 Toast 折叠区（details）
 *   保留排查信息，不参与页面渲染。
 */

/** 原始 RPC/gRPC 异常文本特征（网关透传的内部异常签名） */
const RAW_RPC_TEXT_PATTERNS: RegExp[] = [
  /InactiveRpcError/i,
  /RPC that terminated with/i,
  /StatusCode\.\w+/i,
  /debug_error_string/i,
  /Failed to connect to all addresses/i,
  /Connection refused/i,
  // INT-974：浏览器级网络失败（后端不可达/被拦截时 fetch 直抛 TypeError），
  // 属内部技术异常，降级为友好文案而非直出英文原文
  /failed to fetch/i,
]

/** 是否原始 RPC/gRPC 异常文本（命中任一签名即视为内部异常直出） */
export function isRawRpcErrorText(text: string): boolean {
  if (!text) return false
  return RAW_RPC_TEXT_PATTERNS.some((re) => re.test(text))
}

/** 从对象取值（message / detail / error 字段），空串视为缺失 */
function extractStringField(err: unknown, field: string): string {
  if (err && typeof err === 'object') {
    const v = (err as Record<string, unknown>)[field]
    if (typeof v === 'string' && v.trim()) return v
  }
  return ''
}

/**
 * 供页面/Toast 展示的安全错误消息：
 * 原始 RPC 异常（message 或 detail 命中）→ fallback 固定友好文案；
 * 正常业务错误 → 原样单行化返回（截断 200 字符）。
 */
export function toUserErrorMessage(err: unknown, fallback: string): string {
  const message = extractStringField(err, 'message')
  const detail = extractStringField(err, 'detail')
  if (isRawRpcErrorText(message) || isRawRpcErrorText(detail)) return fallback
  const raw = message || detail
  if (!raw) return fallback
  // 单行化 + 截断：多行/超长异常文本不允许直出，交由固定文案承载
  return raw.replace(/\s+/g, ' ').trim().slice(0, 200)
}

/**
 * 供 Toast 折叠区（details）保留的原始详情：
 * 仅当为原始 RPC 异常时返回（detail 优先，更全），否则为空串不显示折叠区。
 */
export function toUserErrorDetail(err: unknown): string {
  const detail = extractStringField(err, 'detail')
  const message = extractStringField(err, 'message')
  const raw = detail || message
  if (!raw || !isRawRpcErrorText(raw)) return ''
  return raw
}
