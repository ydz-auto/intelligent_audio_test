/**
 * 认证域模型（12_登录与错误页.md §9：错误码枚举单一来源）。
 * 枚举值 = 后端 ErrorCode 原值，禁止改动（frontend/src/domain/enums.ts:150-157 实测口径）。
 */

export enum AuthErrorCode {
  /** 加密校验失败：旧缓存包 / 明文回退 / 公钥轮换（auth_bp.py:103 实测） */
  ENCRYPTION_INVALID = 105,
  /** 用户名或密码错误（401 统一防探测） */
  CREDENTIALS_INVALID = 106,
}

/** 错误码 → 呈现方式映射（§3.4：105 走卡内 Alert、106 走 sonner toast） */
export const AUTH_ERROR_COPY: Record<AuthErrorCode, string> = {
  [AuthErrorCode.ENCRYPTION_INVALID]: '登录加密校验失败，请刷新页面重试',
  [AuthErrorCode.CREDENTIALS_INVALID]: '登录失败：用户名或密码错误',
}

/** 加密初始化失败（前端拿不到公钥，不发起登录请求）——同走卡内 Alert */
export const ENCRYPTION_INIT_FAILED_COPY =
  '登录加密初始化失败，请刷新页面重试'

/** 网络失败/超时统一文案 */
export const NETWORK_FAILED_COPY = '网络异常，请检查连接后重试'

/** OAuth 提供方（对照 GET /auth/oauth/providers 返回：{ id, name, slug, icon }） */
export type OAuthProvider = {
  id: string
  name: string
  slug: string
  /** URL 或类名字符串；mock 态用 key 选取内联图标 */
  icon: string
}
