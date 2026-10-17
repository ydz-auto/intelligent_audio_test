/**
 * 认证真实 API（infrastructure/api 层；接线基座 INT-605）。
 * 对照旧 Vue infrastructure/api/authApi.ts 平移：login / getMe / logout /
 * getAuthMode / fetchEncryptionKey；skipAuthRedirect 白名单与 INT-188 禁明文
 * 回退语义保留。jsencrypt PKCS1v15 降级公钥路径随【接线·认证】卡补装。
 * login 表单 mock 链路仍走 infrastructure/api/auth.ts（认证卡切换真实登录）。
 */
import type { AuthUser } from '@/domain/models/user'
import {
  PasswordEncryptionDisabledError,
  PasswordEncryptionUnavailableError,
  encryptPassword,
  type PasswordEncryptionKey,
} from '@/infrastructure/api/password-encryption'
import { request, type ApiRequestOptions } from '@/infrastructure/api/client'
import type {
  AuthLoginResultDto,
  AuthMeResultDto,
  AuthModeResultDto,
  PasswordEncryptionKeyDto,
} from '@/infrastructure/dto/auth.dto'
import {
  toAuthLoginResult,
  toAuthUserFromMe,
} from '@/infrastructure/dto/auth.dto'

const KEY_CACHE_TTL_MS = 5 * 60_000

let cachedKey: PasswordEncryptionKey | null = null
let cachedAt = 0

/** 登录/注册共用的 RSA 公钥获取（enabled=false 抛 DisabledError 走明文路径；5 分钟缓存） */
async function fetchEncryptionKey(
  options: ApiRequestOptions = {}
): Promise<PasswordEncryptionKey> {
  const now = Date.now()
  if (cachedKey && now - cachedAt < KEY_CACHE_TTL_MS) return cachedKey
  const dto = await request<PasswordEncryptionKeyDto>(
    'GET',
    '/auth/login/encryption-key',
    undefined,
    { ...options, skipAuthRedirect: true }
  )
  if (!dto?.enabled) throw new PasswordEncryptionDisabledError()
  if (!dto.kid || !dto.public_key) throw new PasswordEncryptionUnavailableError()
  const key: PasswordEncryptionKey = { kid: dto.kid, publicKey: dto.public_key }
  // INT-245：降级公钥随响应透传（非安全上下文 jsencrypt 用；未下发时不可降级）
  if (dto.fallback?.kid && dto.fallback?.public_key) {
    key.fallback = { kid: dto.fallback.kid, publicKey: dto.fallback.public_key }
  }
  cachedKey = key
  cachedAt = now
  return key
}

export const authApi = {
  /**
   * 用户名/密码登录（POST /auth/login；表单编码匹配后端 Form(...) 契约；
   * INT-188：加密启用时禁明文回退，加密初始化失败直接抛错引导刷新）。
   * skipAuthRedirect：密码错误 401 不触发全局登出跳转循环。
   */
  async login(
    credentials: { username: string; password: string },
    options: ApiRequestOptions = {}
  ): Promise<{ accessToken: string; user: AuthUser }> {
    const body: Record<string, string> = { username: credentials.username }
    try {
      const enc = await encryptPassword(credentials.password, () =>
        fetchEncryptionKey(options)
      )
      body.password_encrypted = enc.passwordEncrypted
      body.encryption_key_id = enc.encryptionKeyId
    } catch (e) {
      // 仅加密未启用（enabled=false）走明文字段路径；其余失败直接抛
      if (!(e instanceof PasswordEncryptionDisabledError)) throw e
      body.password = credentials.password
    }
    const dto = await request<AuthLoginResultDto>(
      'POST',
      '/auth/login',
      body,
      {
        ...options,
        skipAuthRedirect: true,
        formUrlEncoded: true,
      }
    )
    return toAuthLoginResult(dto)
  },

  /** 当前登录用户信息（GET /auth/me；JWT 由 client 拦截器注入） */
  async getMe(options: ApiRequestOptions = {}): Promise<AuthUser> {
    const dto = await request<AuthMeResultDto>(
      'GET',
      '/auth/me',
      undefined,
      options
    )
    return toAuthUserFromMe(dto)
  },

  /** 登出（POST /auth/logout；JWT 无状态，服务端审计旁路，失败不阻断本地清理） */
  async logout(options: ApiRequestOptions = {}): Promise<void> {
    await request('POST', '/auth/logout', undefined, options)
  },

  /** 当前生效认证模式（GET /auth/mode；公开端点，INT-180 启动自检） */
  async getAuthMode(options: ApiRequestOptions = {}): Promise<string> {
    const dto = await request<AuthModeResultDto>(
      'GET',
      '/auth/mode',
      undefined,
      { ...options, skipAuthRedirect: true }
    )
    return dto.auth_mode ?? ''
  },
}
