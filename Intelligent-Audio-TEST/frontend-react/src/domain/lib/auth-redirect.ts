/**
 * 登录后跳转地址清洗（domain/lib 层，零依赖纯函数；原 features/auth/lib
 * 实现平移，INT-605 会话过期默认跳转共用）。
 * 对齐 doc/UX设计规范/12_登录与错误页.md §1.1：拒绝 // 协议相对、反斜杠、
 * 非 http(s)；仅放行站内路径或同源 URL，默认 /dashboard 由调用方处理。
 */

const allowedRedirectProtocols = new Set(['http:', 'https:'])

export function sanitizeAuthRedirect(
  value: unknown,
  origin: string
): string | null {
  if (typeof value !== 'string') return null

  const target = value.trim()
  if (!target || target.includes('\\') || target.startsWith('//')) return null

  let trustedOrigin: URL
  try {
    trustedOrigin = new URL(origin)
  } catch {
    return null
  }
  if (!allowedRedirectProtocols.has(trustedOrigin.protocol)) return null

  let redirectURL: URL
  try {
    redirectURL = target.startsWith('/')
      ? new URL(target, trustedOrigin.origin)
      : new URL(target)
  } catch {
    return null
  }

  if (
    !allowedRedirectProtocols.has(redirectURL.protocol) ||
    redirectURL.origin !== trustedOrigin.origin
  ) {
    return null
  }

  return `${redirectURL.pathname}${redirectURL.search}${redirectURL.hash}`
}
