/**
 * 注册策略 query（application 层）：GET /auth/registration-policy 公开端点。
 * 注册页据此决定是否渲染邀请码输入（管理员开关变更后即时生效，故不缓存）。
 */
import { useQuery } from '@tanstack/react-query'

import type { RegistrationPolicy } from '@/domain/models/auth'
import { authApi } from '@/infrastructure/api/authApi'

export const REGISTRATION_POLICY_QUERY_KEY = ['auth', 'registration-policy']

export function useRegistrationPolicy() {
  return useQuery<RegistrationPolicy>({
    queryKey: REGISTRATION_POLICY_QUERY_KEY,
    queryFn: () => authApi.getRegistrationPolicy(),
    staleTime: 0,
    // 策略查询失败不阻塞注册表单渲染（后端注册接口仍会兜底校验邀请码）
    retry: 0,
  })
}
