import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { AuthUser } from '@/domain/models/user'
import { authApi } from '@/infrastructure/api/authApi'
import { onSessionExpired } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

/**
 * 认证 store（infrastructure/stores 层；接线基座 INT-605：mock 会话 → 真实
 * getMe/登录态）。token 存取落 infrastructure/storage/auth-token（client 拦截器
 * 同源读取）；登录/登出/会话恢复走 infrastructure/api/authApi；401 + refresh
 * 失效的会话过期由 client 侧通知清空登录态。
 * MOCK_USER / mockLogin 保留供演示预览（页面 mock 链路；完整认证接线见
 * 【接线·认证】卡，届时登录表单切 authApi）。
 */

type AuthState = {
  user: AuthUser | null
  setAuth: (user: AuthUser | null) => void
  /** 真实登录（POST /auth/login → token 落 storage + user 落 store） */
  login: (credentials: { username: string; password: string }) => Promise<void>
  /** 真实登出（POST /auth/logout 审计旁路 + 清 token/user） */
  logout: () => Promise<void>
  /** 会话恢复（token 存在时 GET /auth/me 回填 user；401 由 client 侧清理） */
  hydrateSession: () => Promise<void>
}

/** mock 演示用户：超级管理员，permissions '*' 全通过（04_控制台.md §5 矩阵验证用） */
export const MOCK_USER: AuthUser = {
  id: 'mock-user-001',
  username: 'demo_admin',
  displayName: '演示管理员',
  roleName: '超级管理员',
  permissions: ['*'],
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

/** mock 登录：演示环境任意账号密码均可进入（红线④ mock 预览保留） */
export function mockLogin(username: string): AuthUser {
  return {
    ...MOCK_USER,
    username,
    displayName:
      username === MOCK_USER.username ? MOCK_USER.displayName : username,
  }
}

// 会话过期（401 + refresh 失效）：token 已由 client 侧清，此处仅清空 user 登录态
onSessionExpired(() => {
  useAuthStore.setState({ user: null })
})
