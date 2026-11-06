/**
 * 自助修改密码 API 桩（infrastructure 层，红线④：mock 常量）。
 * 13_个人中心.md §3.5.1/§4.3-1：后端当前**无自助修改密码端点**（auth_bp 仅
 * login/callback/refresh/logout/me；user_bp PUT /users/{id} 系 admin 管他人）。
 * 端点落地前修改密码 UI 入口隐藏，本文件仅保留契约占位，不做任何实现。
 * TODO(后端立项): POST /auth/me/password（当前密码+新密码，走登录加密公钥体系，
 * 新密码长度下限对齐平台 AUTH_PASSWORD_MIN_LENGTH 默认 6）；落点后解除入口隐藏。
 */

/** 自助改密提交契约（未落端点前调用即抛错，防止演示环境出现假成功） */
export async function changeMyPassword(
  _currentPassword: string,
  _newPassword: string
): Promise<void> {
  throw new Error('自助修改密码端点未立项（待后端立项）')
}
