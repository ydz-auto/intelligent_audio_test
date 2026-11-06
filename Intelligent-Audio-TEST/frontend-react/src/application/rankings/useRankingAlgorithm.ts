/**
 * 排行页「页内算法」数据 hook（application 层，INT-442 口径修正后契约：
 * 算法卡片网格 = 每算法一张大卡，数据源 GET /algorithm/definitions 全量）。
 * 订阅页内 store（useRankingAlgorithmStore，localStorage iatp:rankings:v1:algorithm），
 * **不写回全局算法 store**；无 algorithm:read（device_admin/guest/未登录）只读降级条。
 * 榜单按算法过滤待后端立项（ReadModel 暂无算法维度），就绪前榜单全量展示。
 * INT-730 接线：definitions 经 algorithm-config-api.fetchAlgorithmDefinitions 真实端点
 * （client.ts，AlgorithmDefinition 全量 camelCase 形态，含 deviceParams/caseParams
 * 供参数摘要计数；API 参数已迁移到 API 实例作用域，算法侧不再计数）；
 * queryKey 与算法配置页共享 ['algorithm-definitions'] 缓存。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchAlgorithmDefinitions } from '@/infrastructure/api/algorithm-config-api'
import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'
import { useBenchmarkAccess } from '@/application/rankings/useBenchmarkAccess'
import { useRankingAlgorithmStore } from '@/infrastructure/stores/ranking-algorithm-store'

export interface RankingAlgorithmState {
  algorithmType: string | null
  definitions: AlgorithmDefinition[]
  selected: AlgorithmDefinition | undefined
  isLoading: boolean
  /** 无 algorithm:read（device_admin/guest/未登录）——只读降级条 */
  isReadonly: boolean
  /** definitions 拉取失败——整卡值区「--」+「算法详情暂不可用」 */
  isFailed: boolean
  /** 「全部算法」态：store 为 null 或定义不存在 */
  isAllAlgorithms: boolean
}

export function useRankingAlgorithm(): RankingAlgorithmState {
  const { canReadAlgorithm: canRead } = useBenchmarkAccess()
  const algorithmType = useRankingAlgorithmStore((s) => s.algorithmType)
  const defsQuery = useQuery({
    queryKey: ['algorithm-definitions'],
    queryFn: fetchAlgorithmDefinitions,
    staleTime: 30_000,
    enabled: canRead,
  })

  if (!canRead) {
    return {
      algorithmType,
      definitions: [],
      selected: undefined,
      isLoading: false,
      isReadonly: true,
      isFailed: false,
      isAllAlgorithms: !algorithmType,
    }
  }

  const definitions = defsQuery.data ?? []
  const selected = definitions.find((d) => d.type === algorithmType)

  return {
    algorithmType,
    definitions,
    selected,
    isLoading: defsQuery.isLoading && !defsQuery.data,
    isReadonly: false,
    isFailed: defsQuery.isError || !defsQuery.data,
    isAllAlgorithms: !algorithmType || !selected,
  }
}

/** 参数摘要「设备参数 {n} · 用例参数 {k}」；两项全 0/缺失返回空串隐藏 */
export function buildParamSummary(
  definition: AlgorithmDefinition | undefined
): string {
  if (!definition) return ''
  const device = definition.deviceParams?.length ?? 0
  const cases = definition.caseParams?.length ?? 0
  if (device === 0 && cases === 0) return ''
  return `设备参数 ${device} · 用例参数 ${cases}`
}
