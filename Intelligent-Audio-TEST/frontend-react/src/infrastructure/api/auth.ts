import {
  AuthErrorCode,
  type OAuthProvider,
} from '@/domain/models/auth'

/**
 * 认证 API 桩（红线④：mock 常量，不接真实后端）。
 * TODO(API 接线): 对位 infrastructure 平移清单（12_登录与错误页.md §9）——
 * login / register / getMe / listPublicOAuthProviders / fetchEncryptionKey；
 * skipAuthRedirect 白名单与 INT-188 禁明文回退、INT-245 降级公钥语义平移保留。
 */

/** 密码加密不可用（前端拿不到公钥时抛出，不回退明文——authApi.ts:41-48 语义） */
export class PasswordEncryptionUnavailableError extends Error {
  constructor() {
    super('encryption key unavailable')
    this.name = 'PasswordEncryptionUnavailableError'
  }
}

/** 演示用登录失败：携带后端错误码语义，供表单层做 105/106 分流呈现 */
export class MockAuthError extends Error {
  constructor(public code: AuthErrorCode) {
    super(`mock auth error ${code}`)
    this.name = 'MockAuthError'
  }
}

/**
 * RSA 加密公钥桩。
 * TODO(API 接线): GET /auth/login/encryption-key（INT-188：无公钥不发起明文登录）。
 */
export async function fetchEncryptionKey(): Promise<string> {
  // 演示环境恒返回固定公钥指纹；真实接线后缓存 + 轮换降级（INT-245）
  return 'MOCK-RSA-PUBLIC-KEY'
}

/**
 * 密码 RSA 加密桩。
 * TODO(API 接线): JSEncrypt/WebCrypto 加密 → password_encrypted + encryption_key_id。
 */
export async function encryptPassword(
  password: string,
  _publicKey: string
): Promise<{ passwordEncrypted: string; encryptionKeyId: string }> {
  // 桩：仅做长度混淆标记，证明加密链路占位已接（不发明真实加密）
  return {
    passwordEncrypted: `mock-encrypted:${password.length}`,
    encryptionKeyId: 'mock-key-001',
  }
}

/** mock 登录：按演示触发词分流错误码（105/106 文案映射可视化） */
export async function submitLoginMock(
  username: string,
  _passwordEncrypted: string
): Promise<'ok'> {
  if (username === 'error_105') throw new MockAuthError(AuthErrorCode.ENCRYPTION_INVALID)
  if (username === 'error_106') throw new MockAuthError(AuthErrorCode.CREDENTIALS_INVALID)
  return 'ok'
}

/**
 * mock 注册：'closed' 用户名模拟注册开关关闭（403 引导态）。
 * TODO(API 接线): POST /auth/register（403=未开放注册 / 400、409=detail 文案）。
 */
export async function submitRegisterMock(username: string): Promise<'ok'> {
  if (username === 'closed') throw new Error('REGISTRATION_DISABLED')
  return 'ok'
}

/** mock OAuth 提供方（2 个，形态对照真实 schema { id, name, slug, icon }） */
export const MOCK_OAUTH_PROVIDERS: OAuthProvider[] = [
  { id: '1', name: 'GitHub', slug: 'github', icon: 'github' },
  { id: '2', name: '企业统一认证', slug: 'oidc', icon: 'oidc' },
]

/** OAuth 提供方列表桩。TODO(API 接线): GET /auth/oauth/providers（公开端点） */
export async function listPublicOAuthProviders(): Promise<OAuthProvider[]> {
  return MOCK_OAUTH_PROVIDERS
}

/**
 * OAuth authorize 跳转桩（契约：整页 302 → oauth_bp.py:47；回调 302 回 /#/login?oauth_token=…）。
 * TODO(API 接线): window.location.href = `/api/v1/auth/oauth/${slug}/authorize`。
 */
export async function beginOAuthAuthorize(slug: string): Promise<never> {
  throw new Error(`oauth authorize not wired: ${slug}`)
}
