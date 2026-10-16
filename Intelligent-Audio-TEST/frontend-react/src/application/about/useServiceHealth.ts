import { useQuery } from '@tanstack/react-query'

import { toServiceHealthState } from '@/application/status/statusMapper'
import {
  fetchAuthHealth,
  fetchGatewayHealth,
} from '@/infrastructure/api/healthApi'

/**
 * 服务状态查询 hook（application 层）。
 * /health 请求策略（06_关于.md §3.1.1）：进入页面拉一次 + 手动刷新（无轮询）。
 * mock 数据恒成功 → 状态卡正常态；真实接线失败 → 全卡降级「检测中」+ 提示条（§4.4）。
 */
export function useServiceHealth() {
  const gatewayQuery = useQuery({
    queryKey: ['about-health', 'gateway'],
    queryFn: fetchGatewayHealth,
  })
  const authQuery = useQuery({
    queryKey: ['about-health', 'auth'],
    queryFn: fetchAuthHealth,
  })

  const state = toServiceHealthState({
    gateway: gatewayQuery.data,
    auth: authQuery.data,
    gatewayFailed: gatewayQuery.isError,
    authFailed: authQuery.isError,
  })

  return {
    ...state,
    isLoading: gatewayQuery.isLoading || authQuery.isLoading,
    refreshing: gatewayQuery.isRefetching || authQuery.isRefetching,
    refresh: () => {
      void gatewayQuery.refetch()
      void authQuery.refetch()
    },
  }
}
