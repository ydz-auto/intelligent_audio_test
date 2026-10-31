/**
 * 维度内目标参数缓存（`/algorithm/dimension-params`；按 dimensionId 惰性拉取）。
 * 算法编辑模态窗的评估映射与设备弹窗的评估映射共用。
 */
import { useEffect, useRef, useState } from 'react'

import type { DimensionParam } from '@/domain/models/algorithmConfig'
import { fetchDimensionParams } from '@/infrastructure/api/algorithm-config-api'

export function useDimensionParamsMap(
  dimensionIds: string[]
): Record<string, DimensionParam[]> {
  const [cache, setCache] = useState<Record<string, DimensionParam[]>>({})
  const loadedRef = useRef<Set<string>>(new Set())
  const idsKey = dimensionIds.join('|')
  useEffect(() => {
    const ids = [...new Set(dimensionIds.filter((id) => id && !loadedRef.current.has(id)))]
    if (ids.length === 0) return
    let cancelled = false
    for (const id of ids) {
      loadedRef.current.add(id)
      fetchDimensionParams(Number(id))
        .then((params) => {
          if (!cancelled) setCache((c) => ({ ...c, [id]: params }))
        })
        .catch(() => {
          if (!cancelled) setCache((c) => ({ ...c, [id]: [] }))
        })
    }
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey])
  return cache
}
