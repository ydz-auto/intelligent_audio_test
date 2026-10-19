/**
 * 系统设置页接口错误友好降级（INT-900 / INT-858 N2）
 *
 * 后端 auth_service 500（非 JSON 响应体）时，infrastructure/http/client.ts 抛出
 * 「Server returned invalid JSON: 500 Internal Server Error - Failed to execute 'clone' on 'Response'」
 * 之类的原始 JS 错误串。系统设置 IAM 用户/角色/OAuth 三页与登录页不应把这类串直出到页面，
 * 统一回落为固定友好文案 + 重试按钮；业务错误（4xx 带 detail）仍展示后端文案。
 */
export const SERVER_UNAVAILABLE_COPY = '服务暂时不可用，请稍后重试'

/** 判定接口错误是否为服务端/网络层失败（5xx / 非 JSON 响应 / fetch 失败），而非业务 4xx 校验错误 */
export function isServerFailure(e: any): boolean {
  if (!e) return false
  if (typeof e.status === 'number' && e.status >= 500) return true
  const msg = String(e?.message ?? '')
  return /Server returned (invalid JSON|HTML instead of JSON)|Internal Server Error|Failed to fetch|NetworkError|status code 5\d\d/i.test(msg)
}

/** 接口错误 → 页面展示文案：服务端/网络错误回落固定文案；业务错误优先 detail，否则 message/兜底 */
export function friendlyApiError(e: any, fallback: string): string {
  if (isServerFailure(e)) return SERVER_UNAVAILABLE_COPY
  const detail = e?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return String(e?.message ?? fallback)
}
