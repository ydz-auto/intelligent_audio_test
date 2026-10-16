import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasAnyPermission, SYSTEM_SETTINGS_PERMISSIONS } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import SystemSettingsWorkspace from '@/features/system-settings'

/**
 * 系统设置工作区守卫（INT-347 §3.3，对位 newAPI system-settings/route.tsx 超管守卫）：
 * hasAnyPermission(收窄后四码) 不满足 → /403（入口可见性与路由守卫同一权限集合）。
 */
export const Route = createFileRoute('/_authenticated/system-settings')({
  beforeLoad: ({ location }) => {
    const user = useAuthStore.getState().user
    if (!hasAnyPermission(user, [...SYSTEM_SETTINGS_PERMISSIONS])) {
      throw redirect({ to: '/403', search: { from: location.href } })
    }
  },
  component: () => <SystemSettingsWorkspace />,
})
