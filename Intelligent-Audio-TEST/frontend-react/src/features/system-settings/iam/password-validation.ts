/**
 * 用户管理入口的密码校验（INT-1584，纯函数无 UI 依赖，便于单测）。
 * 口径：8–128 位；新建必填、编辑留空表示不修改；一旦填写即校验。
 * 首尾空白先 trim 再计长度（纯空白按空处理），内部空格保留。
 */

export const USER_PASSWORD_MIN_LENGTH = 8
export const USER_PASSWORD_MAX_LENGTH = 128

export const USER_PASSWORD_REQUIRED_MESSAGE = '请输入密码'
export const USER_PASSWORD_LENGTH_MESSAGE = '密码长度需为 8–128 位'

/** 返回空串表示通过。 */
export function validateUserPassword(
  password: string,
  mode: 'create' | 'edit'
): string {
  const value = password.trim()
  if (!value) {
    return mode === 'create' ? USER_PASSWORD_REQUIRED_MESSAGE : ''
  }
  if (
    value.length < USER_PASSWORD_MIN_LENGTH ||
    value.length > USER_PASSWORD_MAX_LENGTH
  ) {
    return USER_PASSWORD_LENGTH_MESSAGE
  }
  return ''
}
