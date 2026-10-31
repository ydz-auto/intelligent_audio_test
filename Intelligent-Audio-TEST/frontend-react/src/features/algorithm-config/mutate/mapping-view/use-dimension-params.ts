/**
 * 维度内目标参数缓存（`/algorithm/dimension-params`；按 dimensionId 惰性拉取）。
 * 算法编辑模态窗的评估映射与设备弹窗的评估映射共用。
 *
 * INT-2203 / INT-2213：本库一个算法有 300+ 维度，旧实现每个响应各触发一次 setCache，
 * 每次都会让整张映射表（近 2000 行）重渲染——展开 Sheet 后十几秒里持续掉帧。
 * 现改为：
 * - 模块级缓存：会话内同一维度只拉一次（切换算法 / 关闭重开都命中）；
 * - 并发 6 拉取，结果合并后只 setState 一次（不再 N 次整表重渲染）；
 * - 调用方只需传「当前视口内用到的维度 id」（映射大表窗口化后通常只有个位数），
 *   滚动到新分组时再增量拉取，不再一次性向 300+ 维度各发一次请求。
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import type { DimensionParam } from '@/domain/models/algorithmConfig'
import { fetchDimensionParams } from '@/infrastructure/api/algorithm-config-api'

/** 维度内参数模块级缓存（dimensionId → 参数列表） */
const dimensionParamsCache = new Map<string, DimensionParam[]>()
/** 窗口尚未测量时按≈一屏预取的分组数（滚动后按视口增量拉取） */
export const DIMENSION_PREVIEW_GROUPS = 8

/** 单批并发上限（同时挂 300+ 请求会被浏览器按域排队拖慢首屏） */
const DIMENSION_PARAMS_CONCURRENCY = 6

export function useDimensionParamsMap(
  dimensionIds: string[]
): Record<string, DimensionParam[]> {
  const [cache, setCache] = useState<Record<string, DimensionParam[]>>(() => {
    const initial: Record<string, DimensionParam[]> = {}
    for (const id of new Set(dimensionIds)) {
      const cached = dimensionParamsCache.get(id)
      if (id && cached) initial[id] = cached
    }
    return initial
  })
  /** 已发起过请求的维度（含缓存命中的），避免重复请求 */
  const requestedRef = useRef<Set<string>>(new Set())
  const mountedRef = useRef(true)
  const dimensionIdsRef = useRef(dimensionIds)
  dimensionIdsRef.current = dimensionIds

  /** 只按「集合内容」触发：同样的 id 集合重复传入不再发请求 */
  const idsKey = useMemo(
    () => [...new Set(dimensionIds.filter(Boolean))].sort().join('|'),
    [dimensionIds]
  )

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    // 先把模块缓存里已有的维度并入状态（滚动/切换时命中缓存不再发请求）
    const cachedNow: Record<string, DimensionParam[]> = {}
    for (const id of new Set(dimensionIdsRef.current)) {
      const cached = dimensionParamsCache.get(id)
      if (id && cached) cachedNow[id] = cached
    }
    if (Object.keys(cachedNow).length > 0) {
      setCache((previous) => ({ ...previous, ...cachedNow }))
    }

    const ids = [...new Set(dimensionIdsRef.current)].filter(
      (id) => id && !dimensionParamsCache.has(id) && !requestedRef.current.has(id)
    )
    if (ids.length === 0) return
    for (const id of ids) requestedRef.current.add(id)

    const run = async () => {
      const results: Record<string, DimensionParam[]> = {}
      let cursor = 0
      const worker = async () => {
        while (cursor < ids.length) {
          const id = ids[cursor]
          cursor += 1
          let params: DimensionParam[] = []
          try {
            params = await fetchDimensionParams(Number(id))
          } catch {
            params = []
          }
          dimensionParamsCache.set(id, params)
          results[id] = params
        }
      }
      await Promise.all(
        Array.from({ length: Math.min(DIMENSION_PARAMS_CONCURRENCY, ids.length) }, worker)
      )
      // 结果已进模块缓存，仍挂载就一次性并入状态（一次渲染，而非每响应一次）
      if (mountedRef.current) {
        setCache((previous) => ({ ...previous, ...results }))
      }
    }
    void run()
  }, [idsKey])

  return cache
}
