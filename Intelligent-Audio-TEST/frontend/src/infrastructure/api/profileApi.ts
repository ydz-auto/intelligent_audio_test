/**
 * 自我资料更新 API module（13_个人中心 §3.4 / 总表 §3.3 F3）
 *
 * 后端无 users/me / auth/self 端点（仅 admin 经 user_bp PUT /users/{id} 管他人）——
 * 本文件为 `// 待接线` 桩：不造数据兜底、不出现假成功（调用即抛「待后端立项」）。
 * 待 FEAT **INT-753** 落地后由【两前端接线·新Vue】卡换成真实请求（PUT /auth/self，语义以后端定稿为准）。
 */
import type { UpdateProfilePayload } from '../../domain/model/profile'

/**
 * 更新当前登录用户资料（自我资料更新 F3 待 FEAT，未落端点前不可用）。
 * 桩契约：真实端点就绪后返回更新后用户信息（或按后端 schema 定稿）。
 */
export async function updateMyProfile(_payload: UpdateProfilePayload): Promise<void> {
  // 待接线 F3：FEAT INT-753 落地后替换为真实请求（PUT /auth/self）
  throw new Error('该功能待后端接口支持（自我资料更新 F3 待 FEAT），暂不可用')
}
