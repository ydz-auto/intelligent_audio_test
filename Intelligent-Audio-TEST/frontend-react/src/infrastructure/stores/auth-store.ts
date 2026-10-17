import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { AuthUser } from '@/domain/models/user'
import { authApi } from '@/infrastructure/api/authApi'
import { onSessionExpired } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

/**
 * 认证 store（infrastructure/stores 层；接线基座 INT-605 落真实登录态、
 * 认证接线 INT-606 落 OAuth 回调登录）。token 存取落
 * infrastructure/storage/auth-token（client 拦截器同源读取）；
 * 登录/登出/OAuth 回调/会话恢复走 infrastructure/api/authApi；
 * 401 + refresh 失效的会话过期由 client 侧通知清空登录态。
 */

type AuthState = {
  user: AuthUser | null
  setAuth: (user: AuthUser | null) => void
  /** 真实登录（POST /auth/login → token 落 storage + user 落 store） */
  login: (credentials: { username: string; password: string }) => Promise<void>
  /** OAuth 回调登录（token 由服务端签发回传 → 落 storage + GET /auth/me 落 store） */
  loginWithToken: (token: string) => Promise<void>
  /** 真实登出（POST /auth/logout 审计旁路 + 清 token/user） */
  logout: () => Promise<void>
  /** 会话恢复（token 存在时 GET /auth/me 回填 user；401 由 client 侧清理） */
  hydrateSession: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      setAuth: (user) => set({ user }),
      login: async (credentials) => {
        const { accessToken, user } = await authApi.login(credentials)
        authTokenStore.set(accessToken)
        set({ user })
      },
      loginWithToken: async (token) => {
        authTokenStore.set(token)
        const user = await authApi.getMe()
        set({ user })
      },
      logout: async () => {
        try {
          await authApi.logout()
        } catch {
          // 登出接口审计旁路（INT-406）；失败不阻断本地清理
        }
        authTokenStore.clear()
        set({ user: null })
      },
      hydrateSession: async () => {
        if (!authTokenStore.get()) return
        try {
          const user = await authApi.getMe()
          set({ user })
        } catch {
          // 401 已由 client 侧触发会话过期清理；其余错误保留现有状态
        }
      },
    }),
    {
      name: 'iatp:auth:v1',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

// 会话过期（401 + refresh 失效）：token 已由 client 侧清，此处仅清空 user 登录态
onSessionExpired(() => {
  useAuthStore.setState({ user: null })
})
