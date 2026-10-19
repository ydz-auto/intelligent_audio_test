// -*- coding: utf-8 -*-
/**
 * 工作台权限判定（INT-736）
 *
 * 总表 §2.6 注4：AUTH_MODE=off 部署（现常驻后端即 off）后端注入 permissions=['*']，
 * 前端无 token/用户，authStore.hasPermission 对空权限集返回 false——若直接按权限码
 * 判定，工作台整区（算法网格/图表/面板）会退化为只读或隐藏，与「off 一切全显」口径不符。
 *
 * 故：getEffectiveAuthMode() === OFF 时全放行；否则走 authStore.hasPermission。
 * 开认证（dev/prod）后自然回落到 RBAC 权限码过滤，无需改动本页。
 */
import { AuthMode, getEffectiveAuthMode } from '../../domain/enums'
import { useAuthStore } from '../../store/authStore'

export function useDashboardPermission() {
  const authStore = useAuthStore()

  function can(perm: string): boolean {
    if (getEffectiveAuthMode() === AuthMode.OFF) return true
    return authStore.hasPermission(perm)
  }

  return { can }
}
