import { useCallback } from 'react'

import {
  hasAnyPermission,
  hasPermission,
} from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 权限判定 hook（application 层）。
 * RBAC 口径：'*' 通配；hasAnyPermission 用于「任一设置域权限」类入口判定。
 */
export function usePermissions() {
  const user = useAuthStore((s) => s.user)

  const check = useCallback(
    (permission: string) => hasPermission(user, permission),
    [user]
  )
  const checkAny = useCallback(
    (permissions: string[]) => hasAnyPermission(user, permissions),
    [user]
  )

  return {
    user,
    hasPermission: check,
    hasAnyPermission: checkAny,
  }
}
