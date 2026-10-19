/**
 * 登录 redirect 消毒（K01）：仅允许站内路径，防开放重定向。
 * 规则：必须以 / 开头；拒绝 //（协议相对）与 scheme:（如 javascript:/http:）。
 */
export function sanitizeRedirect(path: string | null | undefined): string {
  if (!path) return '/dashboard'
  if (!path.startsWith('/')) return '/dashboard'
  if (path.startsWith('//')) return '/dashboard'
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(path)) return '/dashboard'
  // 允许站内任意路径（含查询串），如 /tasks?tab=published
  return path
}
