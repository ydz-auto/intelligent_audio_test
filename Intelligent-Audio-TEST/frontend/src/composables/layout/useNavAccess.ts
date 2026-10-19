/**
 * 导航权限判定（UX设计-VUE 总表 §2.6 注 4）
 *
 * AUTH_MODE=off（现常驻后端即 off）部署一切全显：未登录（无 token、permissions 空）
 * 也按「全权限」放行，与旧 App.vue「未登录显示全部导航」行为一致。
 * 认证开启后按 authStore.hasPermission / hasAnyPermission 逐项过滤。
 */
import { useAuthStore } from '../../store/authStore'
import { AuthMode, getEffectiveAuthMode } from '../../domain/enums'

export function useNavAccess() {
  const authStore = useAuthStore()

  /** 未登录且 AUTH_MODE=off → 全显；否则按权限码判定 */
  function hasNavPermission(perm: string): boolean {
    if (!authStore.isLoggedIn && getEffectiveAuthMode() === AuthMode.OFF) return true
    return authStore.hasPermission(perm)
  }

  /** 未登录且 AUTH_MODE=off → 全显；否则多权限任一 */
  function hasNavAnyPermission(...perms: string[]): boolean {
    if (!authStore.isLoggedIn && getEffectiveAuthMode() === AuthMode.OFF) return true
    return authStore.hasAnyPermission(...perms)
  }

  return { hasNavPermission, hasNavAnyPermission }
}
