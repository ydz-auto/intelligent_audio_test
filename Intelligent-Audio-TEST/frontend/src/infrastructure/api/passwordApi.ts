/**
 * 自助改密 API module（13_个人中心 §3.5.1 / 总表 §3.3 F2）
 *
 * 后端自助改密端点尚未落地（auth_bp 仅 login/callback/refresh/logout/me；
 * user_bp.py 仅 admin PUT /users/{id}，无 self 改密）——
 * 本文件为 `// 待接线` 桩：不造数据兜底、不出现假成功（调用即抛「待后端立项」）。
 * 待 FEAT **INT-752** 落地后由【两前端接线·新Vue】卡换成真实请求
 * （端点路径 PUT /auth/self / POST /auth/change-password 仅作参考，语义以后端定稿为准）。
 */
import type { ChangePasswordPayload } from '../../domain/model/profile'

/**
 * 修改当前登录用户密码（自助改密 F2 待 FEAT，未落端点前不可用）。
 * 桩契约：真实端点就绪后返回 void（或按后端 schema 返回更新后用户信息）。
 */
export async function changeMyPassword(_payload: ChangePasswordPayload): Promise<void> {
  // 待接线 F2：FEAT INT-752 落地后替换为真实请求（PUT /auth/self 或 POST /auth/change-password）
  throw new Error('该功能待后端接口支持（自助改密 F2 待 FEAT），暂不可用')
}
