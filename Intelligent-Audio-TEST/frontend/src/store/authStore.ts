/**
 * 认证 Store — token / permissions / 用户信息
 *
 * 对齐后端 RBAC：AUTH_MODE=off 时后端注入 permissions=['*']，
 * 前端无 token 时也放行（向后兼容）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { HttpStatus } from '../domain/enums'
import type { AuthUser } from '../domain/model'
import { authPort } from '../composables/auth/authPort'

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

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
  const roleName = computed(() => user.value?.roleName || '')
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

  /** 登录：调用 authPort（camelCase Domain 契约）并落库 token/用户 */
  async function login(username: string, password: string): Promise<void> {
    const result = await authPort.login({ username, password })
    setAuth(result.accessToken, result.user)
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
   * 走 composables/auth/authPort 的 authPort（JWT 由 client.ts 拦截器注入），
   * 401 时由 request 抛错，此处捕获后登出
   */
  let initialized = false
  async function init() {
    if (initialized || !token.value) return
    initialized = true
    try {
      // authPort.getMe 已返回 camelCase CurrentUserInfo（Domain），
      // 此处合并至 AuthUser；/auth/me 不含角色名，roleName 兜底取旧会话缓存
      const payload = await authPort.getMe()
      user.value = {
        id: payload.userId ?? user.value?.id ?? 0,
        username: payload.username ?? user.value?.username ?? '',
        roleId: payload.roleId ?? user.value?.roleId ?? null,
        roleName: payload.roleName ?? user.value?.roleName ?? '',
        permissions: payload.permissions ?? user.value?.permissions ?? [],
      }
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    } catch (e: any) {
      if (e?.code === HttpStatus.UNAUTHORIZED) {
        logout()
        return
      }
      // 网络错误等其他异常：保留 localStorage 中的用户信息，下次重试
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
    login,
    setAuth,
    updateUser,
    logout,
    init,
  }
})
