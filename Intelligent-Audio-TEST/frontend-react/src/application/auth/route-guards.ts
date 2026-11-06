import { redirect } from '@tanstack/react-router'

import {
  hasAnyPermission,
  hasPermission,
} from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 路由守卫库（application/auth 层；12_登录与错误页.md §4.3/§9 统一出口）。
 * 各 _authenticated 页面路由 beforeLoad 消费：权限校验失败 → /403?from=<path>
 * （替换旧 Vue「无权限跳首页」的静默行为）；403 页读 from 渲染来源页 muted 小字。
 * 隐藏而非置灰（基座卡 §9.2）：菜单已按权限过滤，本守卫兜 URL 直达与权限变更瞬间。
 */

/** beforeLoad location 的 pathname 子集（TanStack ParsedLocation 结构兼容） */
type GuardLocation = { pathname: string }

/** beforeLoad 校验权限单码：不满足 → /403?from（from 取目标路径 pathname） */
export function requirePermission(
  permission: string,
  location: GuardLocation
): void {
  const user = useAuthStore.getState().user
  if (!hasPermission(user, permission)) {
    throw redirect({ to: '/403', search: { from: location.pathname } })
  }
}

/** beforeLoad 校验权限任一满足：不满足 → /403?from（如系统设置工作区四码集合） */
export function requireAnyPermission(
  permissions: string[],
  location: GuardLocation
): void {
  const user = useAuthStore.getState().user
  if (!hasAnyPermission(user, permissions)) {
    throw redirect({ to: '/403', search: { from: location.pathname } })
  }
}
