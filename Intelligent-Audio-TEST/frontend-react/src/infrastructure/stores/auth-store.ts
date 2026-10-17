import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { AuthUser } from '@/domain/models/user'
import { AUTH_MODE } from '@/domain/models/auth'
import { authApi } from '@/infrastructure/api/authApi'
import { onSessionExpired } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

/**
 * 认证 store（infrastructure/stores 层；接线基座 INT-605 落真实登录态、
 * 认证接线 INT-606 落 OAuth 回调登录）。token 存取落
 * infrastructure/storage/auth-token（client 拦截器同源读取）；
 * 登录/登出/OAuth 回调/会话恢复走 infrastructure/api/authApi；
 * 401 + refresh 失效的会话过期由 client 侧通知清空登录态。
 *
 * AUTH_MODE=off（12_登录与错误页.md §3.1）：后端关闭认证时前端无登录流程，
 * 无 token 也放行——会话恢复 GET /auth/mode 判 off 后 GET /auth/me 回填后端
 * 注入的 dev_user（AuthMiddleware off 分支：username=dev_user、permissions=['*']），
 * 与 Vue AuthMode.OFF 守卫放行口径对齐。守卫与挂载共用 ensureAuthSession
 * 保证首次导航前 user 已就绪（直接进 /dashboard 或点「进入工作台」均可直达）。
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
  /** 会话恢复：有 token → GET /auth/me 回填；无 token 且 AUTH_MODE=off → dev_user 放行 */
  hydrateSession: () => Promise<void>
}

/** 会话引导 promise（守卫/挂载共享；登出/会话过期复位以允许重新引导） */
let sessionBootstrap: Promise<void> | null = null

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
        // 复位引导：登出后再导航允许重新判 AUTH_MODE（off 模式重新 dev_user 放行）
        resetAuthSessionBootstrap()
      },
      hydrateSession: async () => {
        // 有 token：真实会话恢复
        if (authTokenStore.get()) {
          try {
            const user = await authApi.getMe()
            set({ user })
          } catch {
            // 401 已由 client 侧触发会话过期清理；其余错误保留现有状态
          }
          return
        }
        // 无 token：AUTH_MODE=off 开放模式 → GET /auth/me 回填后端注入的 dev_user；
        // 非 off 模式清掉陈旧持久化 user（如历史 off 模式遗留），守卫拦截回登录页。
        // skipAuthRedirect 防模式判定与实际鉴权错位时误触发全局登出跳转。
        try {
          const mode = await authApi.getAuthMode()
          if (mode === AUTH_MODE.OFF) {
            const user = await authApi.getMe({ skipAuthRedirect: true })
            set({ user })
          } else {
            set({ user: null })
          }
        } catch {
          // 模式查询失败（后端未起等）不阻断，保留现有状态
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
  resetAuthSessionBootstrap()
})

/** 复位会话引导（登出/会话过期/测试隔离用；下次 ensureAuthSession 重新引导） */
export function resetAuthSessionBootstrap(): void {
  sessionBootstrap = null
}

/**
 * 会话引导（守卫/挂载共用）：有 token → GET /auth/me 回填；无 token 且
 * AUTH_MODE=off → dev_user 放行。并发调用共享同一 promise 避免重复请求；
 * 引导完成不自动复位（避免守卫每次导航重复 fetch），登出/会话过期时由
 * logout / onSessionExpired 复位重新引导。
 */
export function ensureAuthSession(): Promise<void> {
  if (!sessionBootstrap) {
    sessionBootstrap = useAuthStore.getState().hydrateSession()
  }
  return sessionBootstrap
}
