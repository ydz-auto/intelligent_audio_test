/**
 * 用例卡轮次轴（application 层，15_报告域.md §3.3.7「轮次轴 = Tab」/ §3.5.10「chips 与 Tab 的分工」，INT-1774）。
 *
 * 口径：
 * - **chips 决定可用轮次**（`selectedRounds` = 显示设置「轮次」已选项），**Tab 决定当前展示轮次**；
 * - 候选 Tab = 本用例有数据的轮次 ∩ chips 已选；排序「第 1 轮 … 第 N 轮」→「整体」末位；
 * - 「整体」仅在本用例有 `@overall` 评估数据时出现（照 V9.7.10 `roundTabs`）；
 * - **可用轮次 ≤ 1 时 `roundTabs` 为空**（整条 Tab 栏不渲染）——单轮用例无轮次后缀，多轮用例
 *   chips 只勾 1 个时取值仍用该唯一轮次后缀（`activeRoundTag`），不得回退基础维度键；
 * - **默认激活** = 有「整体」取「整体」，否则第一个有数据轮次（`defaultActiveRoundTag`）；
 *   激活项被 chips 取消 → 回落默认轮次；
 * - 一张用例卡一个轮次轴：叶表 Tab 与评分指标块 / 执行结果块共用（状态在展开区容器，会话内存、
 *   不持久化、不进 URL）；详情 Dialog 自建一份、全显。
 */
import { useMemo, useState } from 'react'

import type { ReportCaseItem } from '@/domain/models/report'
import {
  parseFieldRoundTag,
  parseMetricKey,
  roundTabsFromTags,
  type RoundTab,
} from '@/features/report-view/components/case-report-detail/case-report-utils'

import { extractCaseResourceMetrics } from './case-matrix'

/** 轮次标记来源（执行结果 / 参考 / 用例参数字段） */
export interface RoundTagSource {
  paramCode?: string
  roundNumber?: number
}

/**
 * 默认激活轮次标记：有 `@overall` 取「整体」，否则取第一个有数据的轮次；
 * 无轮次（单轮用例）返回 null（不产 Tab）。取自原 `defaultLeafRounds`（已删除，不再作列集规则）。
 */
export function defaultActiveRoundTag(roundTabs: RoundTab[]): string | null {
  const overall = roundTabs.find((tab) => tab.roundTag === 'overall')
  if (overall) return 'overall'
  return roundTabs.find((tab) => tab.roundTag !== null)?.roundTag ?? null
}

/**
 * 候选轮次 Tab（未做「≤1 不渲染」的收敛）：本用例有数据的轮次 ∩ chips 已选，
 * 「整体」仅在有 `@overall` 评估数据时保留。
 *
 * @param metricKeys 本用例全部指标键（未去轮次后缀）
 * @param sources 结果 / 参考 / 用例参数字段的轮次标记来源
 * @param selectedRounds 显示设置「轮次」已选（`undefined` = 不过滤，详情 Dialog 全显口径）
 */
export function buildCandidateRoundTabs(
  metricKeys: string[],
  sources: RoundTagSource[],
  selectedRounds?: string[]
): RoundTab[] {
  const tags = new Set<string>()
  for (const key of metricKeys) {
    const tag = parseMetricKey(key).roundTag
    if (tag) tags.add(tag)
  }
  for (const source of sources) {
    const tag = parseFieldRoundTag(source.paramCode, source.roundNumber)
    if (tag) tags.add(tag)
  }
  // 「整体」无评估数据时不显示（照 V9.7.10 roundTabs）
  const hasOverallData = metricKeys.some((key) => parseMetricKey(key).roundTag === 'overall')
  if (!hasOverallData) tags.delete('overall')
  const kept = [...tags].filter(
    (tag) => selectedRounds === undefined || selectedRounds.includes(tag)
  )
  return roundTabsFromTags(kept)
}

export interface CaseRoundState {
  /** 轮次 Tab（可用轮次 ≤ 1 为空数组 → 整条 Tab 栏不渲染） */
  roundTabs: RoundTab[]
  /** 当前激活 Tab 的 label（Tab 栏不渲染时为空串） */
  activeRoundTab: string
  setActiveRoundTab: (label: string) => void
  /** 当前激活轮次标记（`null` = 无轮次后缀，按基础维度键取值） */
  activeRoundTag: string | null
  /** 当前 Tab 下的指标键（无轮次标记的键在所有 Tab 下都显示） */
  currentRoundMetricKeys: string[]
  /** 显示设置「轮次」chips 全清（多轮用例）→ 评分指标块 / 叶表指标区「未选择轮次」 */
  noRoundSelected: boolean
}

/**
 * @param caseItem 用例卡（合并后或单行均可）
 * @param selectedRounds 显示设置「轮次」已选轮次标记（不传 = 无 chips 约束／详情 Dialog 全显口径）
 * @param roundsAllCleared 显示设置「轮次」chips 被用户全清（**由 chips 状态显式传入**——
 *   不能用 `selectedRounds.length === 0` 反推：单轮报告本就没有任何轮次 chip，那时空数组
 *   表示「无约束」，不是「全清」）
 */
export function useCaseRoundTabs(
  caseItem: ReportCaseItem,
  selectedRounds?: string[],
  roundsAllCleared = false
): CaseRoundState {
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
  const sources = useMemo<RoundTagSource[]>(() => {
    const list: RoundTagSource[] = (caseItem.algorithmResults ?? []).map((r) => ({
      paramCode: r.paramCode,
      roundNumber: r.roundNumber,
    }))
    for (const p of Object.values(caseItem.referenceParams ?? {})) {
      list.push({ paramCode: p.code, roundNumber: (p as { round_number?: number }).round_number })
    }
    for (const p of Object.values(caseItem.caseParams ?? {})) {
      list.push({ paramCode: p.code, roundNumber: (p as { round_number?: number }).round_number })
    }
    return list
  }, [caseItem.algorithmResults, caseItem.referenceParams, caseItem.caseParams])

  /** 本用例有数据的全部候选轮次（未受 chips 过滤） */
  const allCandidateTabs = useMemo(
    () => buildCandidateRoundTabs(metricKeys, sources),
    [metricKeys, sources]
  )

  /** chips 已选 ∩ 本用例有数据的轮次 */
  const candidateTabs = useMemo(
    () =>
      selectedRounds === undefined
        ? allCandidateTabs
        : allCandidateTabs.filter(
            (tab) => tab.roundTag !== null && selectedRounds.includes(tab.roundTag)
          ),
    [allCandidateTabs, selectedRounds]
  )

  /** 本用例的指标键是否带轮次后缀（多轮用例）；单轮用例为 false → 一律按基础维度键取值 */
  const hasRoundedMetricKeys = useMemo(
    () => metricKeys.some((key) => parseMetricKey(key).roundTag !== null),
    [metricKeys]
  )

  // 可用轮次 ≤ 1 → 整条 Tab 栏不渲染（单轮用例 / chips 只勾 1 个）
  const roundTabs = candidateTabs.length > 1 ? candidateTabs : []

  /** chips 被全清且本用例确有轮次维度的指标 → 「未选择轮次」（单轮用例不受影响） */
  const noRoundSelected = roundsAllCleared && hasRoundedMetricKeys

  const [activeLabel, setActiveLabel] = useState<string | null>(null)

  /**
   * 轮次标记是否有评估数据（照 V9.7.10 `tabHasMetricData`：至少一个资源在该轮次下
   * 有有限数值）。用于默认激活：避免落在只有执行结果、没有指标数据的轮次上
   * （如报告 417 用例仅 `@round:2` 有指标，`@round:1` 只有参考/结果字段）。
   */
  const tagHasMetricData = (roundTag: string): boolean => {
    const keys = metricKeys.filter((key) => parseMetricKey(key).roundTag === roundTag)
    if (keys.length === 0) return false
    return Object.values(resourceMetrics).some((metrics) =>
      keys.some((key) => {
        const value = metrics[key]
        return typeof value === 'number' && Number.isFinite(value)
      })
    )
  }

  const fallbackLabel = useMemo(() => {
    const tag = defaultActiveRoundTag(roundTabs)
    if (tag && tag !== 'overall' && !tagHasMetricData(tag)) {
      const withData = roundTabs.find(
        (tab) => tab.roundTag && tab.roundTag !== 'overall' && tagHasMetricData(tab.roundTag)
      )
      if (withData) return withData.label
    }
    return roundTabs.find((tab) => tab.roundTag === tag)?.label ?? roundTabs[0]?.label ?? ''
  }, [roundTabs, metricKeys, resourceMetrics])

  // 激活项被 chips 取消（不在当前 Tab 集合）→ 回落默认轮次
  const activeRoundTab = useMemo(() => {
    if (roundTabs.length === 0) return ''
    if (activeLabel && roundTabs.some((tab) => tab.label === activeLabel)) return activeLabel
    return fallbackLabel
  }, [roundTabs, activeLabel, fallbackLabel])

  // 唯一可用轮次（Tab 栏不渲染时仍按该轮次后缀取值；无轮次标记 → null 按基础维度键）
  const activeRoundTag = useMemo(() => {
    // 单轮用例：指标键没有任何轮次后缀 → 一律按基础维度键取值（§3.3.7「单轮用例直接展示」）
    if (!hasRoundedMetricKeys) return null
    if (roundTabs.length > 0) {
      return roundTabs.find((tab) => tab.label === activeRoundTab)?.roundTag ?? null
    }
    if (noRoundSelected) return null
    return candidateTabs[0]?.roundTag ?? null
  }, [hasRoundedMetricKeys, roundTabs, activeRoundTab, noRoundSelected, candidateTabs])

  const currentRoundMetricKeys = useMemo(() => {
    if (activeRoundTag) {
      return metricKeys.filter((key) => {
        const { roundTag } = parseMetricKey(key)
        return roundTag === null || roundTag === activeRoundTag
      })
    }
    // 无激活轮次：chips 全清 → 只剩无轮次标记的键；全显（Dialog）→ 全部键
    if (noRoundSelected) return metricKeys.filter((key) => parseMetricKey(key).roundTag === null)
    if (selectedRounds === undefined) return metricKeys
    return metricKeys.filter((key) => {
      const { roundTag } = parseMetricKey(key)
      return roundTag === null || selectedRounds.includes(roundTag)
    })
  }, [metricKeys, activeRoundTag, noRoundSelected, selectedRounds])

  return {
    roundTabs,
    activeRoundTab,
    setActiveRoundTab: setActiveLabel,
    activeRoundTag,
    currentRoundMetricKeys,
    noRoundSelected,
  }
}
