/**
 * 自助改密 API module（13_个人中心 §3.5.1 / 总表 §3.3 F2）
 *
 * POST /api/v1/auth/change-password（INT-794 方案 A）：
 * - 鉴权为「当前登录用户本人」（JWT user_id 注入），非 admin 管他人；
 * - body 复用登录 RSA 公钥体系：current_password_encrypted +
 *   new_password_encrypted + encryption_key_id（加密开关关闭时回退明文
 *   current_password / new_password，与登录/注册同口径）；
 * - 原密码错误 → 401 + code:106 AUTH_CREDENTIALS_INVALID；
 *   新密码长度不足 AUTH_PASSWORD_MIN_LENGTH（默认 6）→ 400；
 * - 成功 → 200 + notice（提示清 token 重新登录）。
 */
import { request, type RequestOptions } from '../http/client'
import {
  encryptPassword,
  PasswordEncryptionDisabledError,
} from '../../utils/passwordEncryption'
import { fetchEncryptionKey } from './authApi'
import type { ChangePasswordPayload } from '../../domain/model/profile'

/**
 * 修改当前登录用户密码（自助改密 F2）。
 * 成功返回 void；失败抛错（`e.detail` / `e.message` 为后端文案，
 * 401 原密码错误 / 400 长度不足）。
 */
export async function changeMyPassword(
  payload: ChangePasswordPayload,
  options: RequestOptions = {},
): Promise<void> {
  const body: Record<string, unknown> = {}
  try {
    const encCurrent = await encryptPassword(payload.currentPassword, () => fetchEncryptionKey(options))
    const encNew = await encryptPassword(payload.newPassword, () => fetchEncryptionKey(options))
    body.current_password_encrypted = encCurrent.passwordEncrypted
    body.new_password_encrypted = encNew.passwordEncrypted
    body.encryption_key_id = encNew.encryptionKeyId
  } catch (e) {
    // INT-188：加密启用时禁止明文兜底（后端加密开启时明文必被拒，
    // 形成"必然失败且无解释"陷阱）——仅加密未启用（enabled=false）走明文字段路径
    if (!(e instanceof PasswordEncryptionDisabledError)) {
      throw e
    }
    body.current_password = payload.currentPassword
    body.new_password = payload.newPassword
  }
  await request('POST', '/auth/change-password', body, {
    ...options,
    // 改密 401 = 原密码错误（AUTH_CREDENTIALS_INVALID），非会话过期：
    // 跳过 client.ts 401 自动登出/跳转，让错误文案留在改密模态框内展示
    // （与 authApi.login 的 skipAuthRedirect 同语义，INT-622 同源防护）
    skipAuthRedirect: true,
  })
}
