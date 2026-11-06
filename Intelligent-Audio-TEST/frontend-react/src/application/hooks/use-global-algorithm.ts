/**
 * 全局算法 store 的 application 层封装（DDD 依赖单向：interfaces/features 不直连 infrastructure/stores）。
 * 读/写全局算法（localStorage iatp:algorithm:v1），供报告中心/展示页算法大卡联动消费。
 */
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'

export function useGlobalAlgorithm() {
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)

  return { algorithmId, setAlgorithmId }
}
