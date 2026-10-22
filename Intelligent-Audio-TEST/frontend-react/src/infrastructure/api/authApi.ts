/**
 * 认证真实 API（infrastructure/api 层；接线基座 INT-605 + 认证接线 INT-606）。
 * 对照旧 Vue infrastructure/api/authApi.ts 平移：login / register / getMe /
 * logout / getAuthMode / listPublicOAuthProviders / getOAuthAuthorizeUrl /
 * fetchEncryptionKey；skipAuthRedirect 白名单与 INT-188 禁明文回退、INT-245
 * 降级公钥语义逐字保留。jsencrypt PKCS1v15 降级公钥路径（http+LAN-IP 非安全
 * 上下文）见 password-encryption.ts：非安全上下文当前收敛为不可用，不回退明文。
 */
import type { OAuthProvider } from '@/domain/models/auth'
import type { AuthUser } from '@/domain/models/user'
import { request, type ApiRequestOptions } from '@/infrastructure/api/client'
import type {
  AuthLoginResultDto,
  AuthMeResultDto,
  AuthModeResultDto,
  PasswordEncryptionKeyDto,
  PublicOAuthProvidersResultDto,
  RegisterResultDto,
} from '@/infrastructure/dto/auth.dto'
import {
  toAuthLoginResult,
  toAuthUserFromMe,
  toOAuthProviderPublicList,
} from '@/infrastructure/dto/auth.dto'
import {
  PasswordEncryptionDisabledError,
  PasswordEncryptionUnavailableError,
  encryptPassword,
  type PasswordEncryptionKey,
} from '@/infrastructure/api/password-encryption'

const KEY_CACHE_TTL_MS = 5 * 60_000

let cachedKey: PasswordEncryptionKey | null = null
let cachedAt = 0

/** 重置公钥缓存（登出/测试隔离用；5 分钟 TTL 语义保留） */
export function resetEncryptionKeyCache(): void {
  cachedKey = null
  cachedAt = 0
}

/** 登录/注册共用的 RSA 公钥获取（enabled=false 抛 DisabledError 走明文路径；5 分钟缓存） */
export async function fetchEncryptionKey(
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

/**
 * 登录/注册共用：密码 RSA 加密 → 密文与 keyId。
 * 加密初始化失败抛 PasswordEncryptionUnavailableError（INT-188 禁明文回退，
 * 由调用方呈现卡内 Alert）；仅后端 enabled=false 时抛 DisabledError 走明文路径。
 */
async function encryptCredentials(
  password: string,
  options: ApiRequestOptions
): Promise<
  | { mode: 'encrypted'; passwordEncrypted: string; encryptionKeyId: string }
  | { mode: 'plain'; password: string }
> {
  try {
    const enc = await encryptPassword(password, () => fetchEncryptionKey(options))
    return {
      mode: 'encrypted',
      passwordEncrypted: enc.passwordEncrypted,
      encryptionKeyId: enc.encryptionKeyId,
    }
  } catch (e) {
    // 仅加密未启用（enabled=false）走明文字段路径；其余失败直接抛
    if (!(e instanceof PasswordEncryptionDisabledError)) throw e
    return { mode: 'plain', password }
  }
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
    const enc = await encryptCredentials(credentials.password, options)
    const body: Record<string, string> = { username: credentials.username }
    if (enc.mode === 'encrypted') {
      body.password_encrypted = enc.passwordEncrypted
      body.encryption_key_id = enc.encryptionKeyId
    } else {
      body.password = enc.password
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

  /**
   * 自助注册（POST /auth/register；JSON body，与 login 同链 RSA 加密；
   * 注册开关关闭时后端回 403，由表单层切引导态）。成功后调用方引导登录。
   * INT-285 口径②：email 必填（后端 400 兜底）。
   */
  async register(
    payload: { username: string; password: string; email: string },
    options: ApiRequestOptions = {}
  ): Promise<{ userId: number }> {
    const enc = await encryptCredentials(payload.password, options)
    const body: Record<string, unknown> = {
      username: payload.username,
      email: payload.email.trim(),
    }
    if (enc.mode === 'encrypted') {
      body.password_encrypted = enc.passwordEncrypted
      body.encryption_key_id = enc.encryptionKeyId
    } else {
      body.password = enc.password
    }
    const dto = await request<RegisterResultDto>(
      'POST',
      '/auth/register',
      body,
      { ...options, skipAuthRedirect: true }
    )
    return { userId: dto?.user_id ?? 0 }
  },

  /**
   * 当前登录用户信息（GET /auth/me；JWT 由 client 拦截器注入）。
   * fallbackRoleName：/auth/me 契约无 role_name（INT-1226），由调用方传入
   * 会话缓存角色码，DTO 层照 ROLE_META 映射中文名，不因缺字段清空。
   */
  async getMe(
    options: ApiRequestOptions = {},
    fallbackRoleName = ''
  ): Promise<AuthUser> {
    const dto = await request<AuthMeResultDto>(
      'GET',
      '/auth/me',
      undefined,
      options
    )
    return toAuthUserFromMe(dto, fallbackRoleName)
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

  /**
   * 已启用 OAuth 提供方（GET /auth/oauth/providers，公开端点；登录页动态渲染）。
   * 空数组由 UI 整区不渲染（12_登录与错误页.md §3.5）。
   */
  async listPublicOAuthProviders(
    options: ApiRequestOptions = {}
  ): Promise<OAuthProvider[]> {
    const dto = await request<PublicOAuthProvidersResultDto>(
      'GET',
      '/auth/oauth/providers',
      undefined,
      { ...options, skipAuthRedirect: true }
    )
    return toOAuthProviderPublicList(dto?.providers ?? [])
  },

  /**
   * OAuth 授权跳转地址（oauth_bp.py:47 契约：整页 302 跳提供方；
   * intent=bind 绑定流程归个人中心卡 INT-358，登录页只用 login）。
   */
  getOAuthAuthorizeUrl(slug: string, intent: 'login' | 'bind' = 'login'): string {
    const base = `/api/v1/auth/oauth/${encodeURIComponent(slug)}/authorize`
    return intent === 'bind' ? `${base}?intent=bind` : base
  },

  /**
   * OAuth 授权跳转（本页跳转不新标签，INT-285 口径③；整页 302 离开当前页，
   * 后续由回调 302 回登录页消化 oauth_token/oauth_error，无需调用方处理）。
   */
  beginOAuthAuthorize(slug: string, intent: 'login' | 'bind' = 'login'): void {
    window.location.assign(this.getOAuthAuthorizeUrl(slug, intent))
  },
}
