/**
 * 认证 Store — token / permissions / 用户信息
 *
 * 对齐后端 RBAC：AUTH_MODE=off 时后端注入 permissions=['*']，
 * 前端无 token 时也放行（向后兼容）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { HttpStatus } from '@/shared/types/enums'

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

interface AuthUser {
  id: number
  username: string
  role_id: number | null
  role_name: string
  permissions: string[]
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<AuthUser | null>(
    (() => {
      try {
        const raw = localStorage.getItem(USER_KEY)
        return raw ? JSON.parse(raw) as AuthUser : null
      } catch {
        return null
      }
    })()
  )

  const isLoggedIn = computed(() => !!token.value)
  const permissions = computed<string[]>(() => user.value?.permissions || [])
  const roleName = computed(() => user.value?.role_name || '')
  const username = computed(() => user.value?.username || '')

  /** 检查是否拥有指定权限（支持 * 通配） */
  function hasPermission(perm: string): boolean {
    const perms = permissions.value
    if (perms.includes('*')) return true
    return perms.includes(perm)
  }

  /** 检查是否拥有给定权限之一 */
  function hasAnyPermission(...perms: string[]): boolean {
    const userPerms = permissions.value
    if (userPerms.includes('*')) return true
    return perms.some(p => userPerms.includes(p))
  }

  /** 登录成功后设置 token 和用户信息 */
  function setAuth(t: string, u: AuthUser) {
    token.value = t
    user.value = u
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(u))
  }

  /** 从 /auth/me 刷新用户信息 */
  function updateUser(u: Partial<AuthUser>) {
    if (user.value) {
      user.value = { ...user.value, ...u }
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    }
  }

  /** 登出 */
  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  /**
   * 应用启动时调用：若 token 存在则拉取最新用户信息。
   * - AUTH_MODE=off 时无 token，直接返回
   * - token 失效（401）则登出
   * 使用 fetch 而非 http.ts，避免循环依赖与拦截器递归
   */
  let initialized = false
  async function init() {
    if (initialized || !token.value) return
    initialized = true
    try {
      const resp = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      if (resp.status === HttpStatus.UNAUTHORIZED) {
        logout()
        return
      }
      if (!resp.ok) return
      const data = await resp.json()
      // /auth/me 返回 {user_id, username, role_id, permissions}（被 to_response 透传）
      const payload = data.data ?? data
      user.value = {
        id: payload.user_id ?? payload.id ?? 0,
        username: payload.username ?? '',
        role_id: payload.role_id ?? null,
        role_name: payload.role_name ?? user.value?.role_name ?? '',
        permissions: payload.permissions ?? [],
      }
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    } catch {
      // 网络错误：保留 localStorage 中的用户信息，下次重试
      initialized = false
    }
  }

  return {
    token,
    user,
    isLoggedIn,
    permissions,
    roleName,
    username,
    hasPermission,
    hasAnyPermission,
    setAuth,
    updateUser,
    logout,
    init,
  }
})
