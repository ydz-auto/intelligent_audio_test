/**
 * 当前认证模式 query（application 层，12_登录与错误页.md §3.1）：
 * GET /auth/mode 公开端点（INT-180 启动自检数据源），AUTH_MODE=off 时
 * 登录页顶部渲染开放模式 Alert。off/dev/prod 枚举回原值。
 */
import { useQuery } from '@tanstack/react-query'

import { authApi } from '@/infrastructure/api/authApi'

/** 认证模式枚举单一来源在 domain/models/auth.ts（auth-store 守卫判 off 同源引用） */
export { AUTH_MODE } from '@/domain/models/auth'

export const AUTH_MODE_QUERY_KEY = ['auth', 'mode']

export function useAuthMode() {
  return useQuery<string>({
    queryKey: AUTH_MODE_QUERY_KEY,
    queryFn: () => authApi.getAuthMode(),
    staleTime: 5 * 60_000,
    // 模式查询失败（后端未起等）不阻塞登录页渲染
    retry: 0,
  })
}
