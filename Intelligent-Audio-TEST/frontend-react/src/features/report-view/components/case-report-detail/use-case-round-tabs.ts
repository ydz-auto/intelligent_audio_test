/**
 * 用例卡片轮次 Tab 共享状态（块一/块三共用 activeRoundTab，照 TestCaseReportDetail）。
 * roundTabs：指标 key @round:N/@overall + 结果/参考/用例参数 round 标记装配；
 * 无轮次标记但有数据 → 单个「指标」Tab；「整体」无评估数据时不显示（照 V9.7.10 roundTabs:1154）。
 */
import { useMemo, useState } from 'react'

import { extractCaseResourceMetrics } from '@/application/report-view/case-matrix'
import type { ReportCaseItem } from '@/domain/models/report'

import {
  buildRoundTabs,
  parseMetricKey,
  parseFieldRoundTag,
  type RoundTab,
} from './case-report-utils'

export function useCaseRoundTabs(caseItem: ReportCaseItem) {
  const resourceMetrics = useMemo(() => extractCaseResourceMetrics(caseItem), [caseItem])

  // 指标 key 集合（资源级去重）
  const metricKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const metrics of Object.values(resourceMetrics)) {
      for (const key of Object.keys(metrics)) keys.add(key)
    }
    return [...keys]
  }, [resourceMetrics])

  // 结果/参考/用例参数轮次标记来源
  const sources = useMemo(() => {
    const list: { paramCode?: string; roundNumber?: number }[] = [
      ...(caseItem.algorithmResults ?? []).map((r) => ({
        paramCode: r.paramCode,
        roundNumber: r.roundNumber,
      })),
    ]
    for (const p of Object.values(caseItem.referenceParams ?? {})) {
      list.push({ paramCode: p.code, roundNumber: (p as { round_number?: number }).round_number })
    }
    for (const p of Object.values(caseItem.caseParams ?? {})) {
      list.push({ paramCode: p.code, roundNumber: (p as { round_number?: number }).round_number })
    }
    return list
  }, [caseItem.algorithmResults, caseItem.referenceParams, caseItem.caseParams])

  const hasAnyField =
    metricKeys.length > 0 || (caseItem.algorithmResults?.length ?? 0) > 0

  // 有数据但无任何轮次标记 → 单个「指标」Tab（roundTag null，全量展示）
  const roundTabs = useMemo<RoundTab[]>(() => {
    const tabs = buildRoundTabs(metricKeys, sources)
    if (tabs.length === 1 && tabs[0].roundTag === 'overall' && !hasAnyField) {
      return []
    }
    if (tabs.length === 1 && tabs[0].roundTag === 'overall' && hasAnyField && !metricKeys.some((k) => k.includes('@'))) {
      return [{ key: 'all', label: '指标', roundTag: null, order: 0 }]
    }
    // 「整体」无评估数据时不显示（照 V9.7.10）
    const hasOverallData = metricKeys.some((k) => parseMetricKey(k).roundTag === 'overall')
    if (!hasOverallData) {
      return tabs.filter((t) => t.roundTag !== 'overall')
    }
    return tabs
  }, [metricKeys, sources, hasAnyField])

  const [activeRoundTab, setActiveRoundTab] = useState(roundTabs[0]?.label ?? '整体')

  // 当前 Tab 对应的指标 key（无轮次标记的 key 在所有 Tab 下都显示；「指标」Tab 显示全部）
  const currentRoundMetricKeys = useMemo(() => {
    const tab = roundTabs.find((t) => t.label === activeRoundTab)
    if (!tab) return metricKeys
    if (tab.roundTag === null) return metricKeys
    return metricKeys.filter((k) => {
      const { roundTag } = parseMetricKey(k)
      if (roundTag === null) return true
      return roundTag === tab.roundTag
    })
  }, [roundTabs, activeRoundTab, metricKeys])

  // 当前轮次标记（供结果/参考/用例参数过滤）
  const activeRoundTag = useMemo(
    () => roundTabs.find((t) => t.label === activeRoundTab)?.roundTag ?? null,
    [roundTabs, activeRoundTab]
  )

  return {
    roundTabs,
    activeRoundTab,
    setActiveRoundTab,
    currentRoundMetricKeys,
    activeRoundTag,
  }
}

/** 工具：读字段轮次标记（供组件内过滤复用） */
export { parseFieldRoundTag }
