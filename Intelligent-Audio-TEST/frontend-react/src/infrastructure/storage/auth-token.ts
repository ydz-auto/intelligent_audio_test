/**
 * 登录态 JWT 存取（infrastructure/storage 层；接线基座 INT-605）。
 * client 请求拦截器与 auth-store 共用的唯一 token 读写口：
 * 登录后落此 storage，请求自动注入 Authorization: Bearer。
 * localStorage 单键，iatp 前缀（与 auth-store zustand persist 的 user 分离）。
 */
const TOKEN_KEY = 'iatp:auth:token:v1'

export const authTokenStore = {
  /** 当前 token（无登录态返回 null） */
  get(): string | null {
    try {
      return window.localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token: string): void {
    try {
      window.localStorage.setItem(TOKEN_KEY, token)
    } catch {
      // 存储不可用（隐私模式等）静默丢弃，登录态仅存内存
    }
  },
  clear(): void {
    try {
      window.localStorage.removeItem(TOKEN_KEY)
    } catch {
      // 同上
    }
  },
}
