/**
 * 系统选项 query（application 层）：KV 全量拉取 + 类型化解析（对齐 newAPI
 * use-system-options 实测：布尔/数字/数组安全解析失败回退默认）。
 * staleTime 5min（对齐 use-system-options.ts）；保存后 invalidate 见 use-update-option。
 */
import { useQuery } from '@tanstack/react-query'

import { hasPermission } from '@/domain/models/user'
import {
  getSystemOptions,
  SYSTEM_OPTIONS_QUERY_KEY,
} from '@/infrastructure/api/optionApi'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

export function useSystemOptions() {
  const user = useAuthStore((s) => s.user)
  // INT-1225：/api/option/ 为 option:read 鉴权端点，公开页站头（匿名）也会挂载
  // useNotifications → 本 hook——匿名不拉取（401 无意义且落控制台 SEVERE）。
  // INT-1585：已登录但无 option:read（guest 等低权限角色）同样不发请求，
  // 否则每次整页加载全局站头都会打出 403 SEVERE；消费方落到默认值/无权限态。
  // 门禁只翻转 enabled，queryKey 恒定（避免缓存分裂）。'*' 由 hasPermission 统一处理。
  const canReadOptions = hasPermission(user, 'option:read')

  return useQuery({
    queryKey: [...SYSTEM_OPTIONS_QUERY_KEY],
    queryFn: getSystemOptions,
    staleTime: 5 * 60_000,
    enabled: canReadOptions,
  })
}
