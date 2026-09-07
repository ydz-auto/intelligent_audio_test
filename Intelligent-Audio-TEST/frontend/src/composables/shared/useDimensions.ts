import { ref } from 'vue'
import { evaluationPort } from '../evaluation/evaluationPort'
import type { EvaluationDimension } from '../../domain'

const dimensionsCache = ref<EvaluationDimension[]>([])
const isLoading = ref(false)
const lastFetchTime = ref<number>(0)
const CACHE_DURATION = 5 * 60 * 1000

export function useDimensions() {
  async function fetchAllDimensions(options: {
    forceRefresh?: boolean
    categoryId?: number
    search?: string
    algorithmType?: string
  } = {}): Promise<EvaluationDimension[]> {
    const now = Date.now()
    const shouldUseCache =
      !options.forceRefresh &&
      dimensionsCache.value.length > 0 &&
      now - lastFetchTime.value < CACHE_DURATION

    if (shouldUseCache) {
      return dimensionsCache.value
    }

    isLoading.value = true
    try {
      const allDimensions: EvaluationDimension[] = []
      const byId = new Map<number | string, EvaluationDimension>()
      let page = 1
      let pages = 1

      while (page <= pages) {
        const params: Record<string, any> = { page, perPage: 200 }
        if (options.categoryId) params.categoryId = options.categoryId
        if (options.search) params.search = options.search
        if (options.algorithmType) params.algorithmType = options.algorithmType

        const res = await evaluationPort.getAll(params)
        const items: EvaluationDimension[] = Array.isArray(res?.items) ? res.items : []
        pages = typeof res?.pages === 'number' ? res.pages : pages

        for (const dim of items) {
          if (!dim?.id || !dim?.name) continue
          // 从 requiredInputs 推导 requiresAudio 标记
          const reqInputs = dim.requiredInputs
          if (Array.isArray(reqInputs)) {
            (dim as any).requiresAudio = reqInputs.some((p: any) => p?.fieldType === 'audio' && p?.paramDirection === 'input')
          }
          if (!byId.has(dim.id)) {
            byId.set(dim.id, dim)
            allDimensions.push(dim)
          }
        }

        if (items.length < 200) break
        page += 1
      }

      dimensionsCache.value = allDimensions
      lastFetchTime.value = now
      return allDimensions
    } finally {
      isLoading.value = false
    }
  }

  async function fetchDimensionsByAlgorithmType(algorithmType: string): Promise<EvaluationDimension[]> {
    isLoading.value = true
    try {
      const res = await evaluationPort.getOptions({ algorithmType })
      const dimensions = res?.dimensions || []
      return dimensions
    } finally {
      isLoading.value = false
    }
  }

  function getDimensionsByAlgorithmType(algorithmType: string): EvaluationDimension[] {
    return dimensionsCache.value.filter(dim => {
      const algorithms = dim.associatedAlgorithms
      return algorithms?.some(
        (algo) => algo.algorithmType === algorithmType
      )
    })
  }

  function clearCache() {
    dimensionsCache.value = []
    lastFetchTime.value = 0
  }

  return {
    dimensions: dimensionsCache,
    isLoading,
    fetchAllDimensions,
    fetchDimensionsByAlgorithmType,
    getDimensionsByAlgorithmType,
    clearCache
  }
}
