/**
 * 自我资料更新 API module（13_个人中心 §3.4 / 总表 §3.3 F3）
 *
 * PUT /api/v1/auth/self（INT-792）：
 * - 鉴权：request.state.user_id 为本人（operator_id 同值），
 *   不要求 user:update（那是 admin 管他人）；
 * - 可编辑字段仅 email；body 携带 username 等其他字段 → 400 拒绝；
 * - email 空串 = 不修改（对齐 admin UpdateUser 空串语义）；
 * - 邮箱格式网关侧校验（auth_service 服务端二次校验）。
 */
import { request, type RequestOptions } from '../http/client'
import type { UpdateProfilePayload } from '../../domain/model/profile'

/**
 * 更新当前登录用户资料（自我资料更新 F3）。
 * 成功返回 void；失败抛错（`e.detail` / `e.message` 为后端文案，
 * 400 格式错误 / 非法字段）。
 */
export async function updateMyProfile(
  payload: UpdateProfilePayload,
  options: RequestOptions = {},
): Promise<void> {
  await request(
    'PUT',
    '/auth/self',
    { email: payload.email?.trim() ?? '' },
    options,
  )
}
