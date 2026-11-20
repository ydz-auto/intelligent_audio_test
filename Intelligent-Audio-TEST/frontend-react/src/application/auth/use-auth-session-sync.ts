/**
 * 登录会话权限同步（application 层用例 hook）。
 *
 * JWT 的权限是登录时快照；管理端调整角色/权限后，后端经实时权限解析
 * 已按新权限鉴权（见 api_gateway/infrastructure/permission_cache.py），
 * 前端菜单与按钮还需同步刷新——切回标签页立即刷新，停留页面时按固定
 * 间隔兜底刷新，均走 /auth/me 静默回填，用户无需重新登录。
 */
import { useEffect } from 'react'

import { refreshAuthSession } from '@/infrastructure/stores/auth-store'

/** 前端会话同步间隔（毫秒）：仅兜底，切回标签页会立即同步一次 */
export const AUTH_SESSION_SYNC_INTERVAL_MS = 60_000

export function useAuthSessionSync() {
  useEffect(() => {
    const sync = () => {
      void refreshAuthSession()
    }
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') sync()
    }
    const timer = window.setInterval(sync, AUTH_SESSION_SYNC_INTERVAL_MS)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])
}
