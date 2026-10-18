import { useQuery } from '@tanstack/react-query'

import { toServiceHealthState } from '@/application/status/statusMapper'
import { fetchSystemHealth } from '@/infrastructure/api/healthApi'

/**
 * 服务状态查询 hook（application 层）。
 * /api/v1/system/health 请求策略（06_关于.md §3.1.1）：进入页面拉一次 + 手动刷新（无轮询）。
 * 汇总端点未落地（待 INT-766）→ 请求失败 → 全卡降级「检测中」+ 提示条（§4.4），
 * 不显示 mock「正常」；端点落地后同一 hook 直接出真实健康数据。
 */
export function useServiceHealth() {
  const query = useQuery({
    queryKey: ['about-health', 'system'],
    queryFn: fetchSystemHealth,
  })

  const state = toServiceHealthState({
    gateway: query.data?.gateway,
    auth: query.data?.auth,
    gatewayFailed: query.isError,
    authFailed: query.isError,
  })

  return {
    ...state,
    isLoading: query.isLoading,
    refreshing: query.isRefetching,
    refresh: () => {
      void query.refetch()
    },
  }
}
