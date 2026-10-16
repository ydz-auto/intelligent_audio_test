/**
 * 「当前算法」大卡数据 hook（application 层，INT-436/INT-442 复用契约）。
 * 当前算法详情：全局 store（localStorage iatp:algorithm:v1）× GET /algorithm/definitions
 * （algorithm:read，AlgorithmDefinitionDto）按 type 解析；无权限（device_admin/guest）只读降级
 * ——仅显示存储原值（type 码或「全部算法」），不杜撰中文名。
 */
import { useQuery } from '@tanstack/react-query'

import { hasPermission } from '@/domain/models/user'
import {
  MOCK_ALGORITHM_DEFINITIONS,
  type MockAlgorithmDefinition,
} from '@/infrastructure/mock/reports-mock'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

export type CurrentAlgorithmState = {
  algorithmType: string | null
  definition: MockAlgorithmDefinition | undefined
  isLoading: boolean
  isReadonly: boolean
  /** 定义拉取失败（algorithm:read 403 / 网络异常）——仅显示 store 原值 */
  isFailed: boolean
  /** 「全部算法」态：store 无值或定义不存在 */
  isAllAlgorithms: boolean
}

/** GET /algorithm/definitions（algorithm:read；mock 常量，TODO(API 接线) 换真实端点） */
async function fetchAlgorithmDefinitions(): Promise<MockAlgorithmDefinition[]> {
  return MOCK_ALGORITHM_DEFINITIONS
}

export function useCurrentAlgorithm(): CurrentAlgorithmState {
  const user = useAuthStore((s) => s.user)
  const algorithmType = useAlgorithmStore((s) => s.algorithmId)

  const canRead = hasPermission(user, 'algorithm:read')
  const defsQuery = useQuery({
    queryKey: ['algorithm', 'definitions'],
    queryFn: fetchAlgorithmDefinitions,
    staleTime: 5 * 60_000,
    enabled: canRead,
  })

  if (!canRead) {
    return {
      algorithmType: algorithmType ?? null,
      definition: undefined,
      isLoading: false,
      isReadonly: true,
      isFailed: false,
      isAllAlgorithms: !algorithmType,
    }
  }

  const definition = defsQuery.data?.find((d) => d.type === algorithmType)

  return {
    algorithmType: algorithmType ?? null,
    definition,
    isLoading: defsQuery.isLoading && !defsQuery.data,
    isReadonly: false,
    isFailed: defsQuery.isError || !defsQuery.data,
    isAllAlgorithms: !algorithmType || !definition,
  }
}
