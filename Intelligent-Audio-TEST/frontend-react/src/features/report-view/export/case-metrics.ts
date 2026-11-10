/**
 * 导出产物用例卡的「可筛选 / 可排序」数据（INT-2434 二轮：负责人反馈「具体用例卡片功能不完整、
 * 筛选功能不完整」）。
 *
 * 页面筛选走服务端（`POST /reports/{id}/cases/search`），导出产物没有后端——快照管线把每张卡
 * 的筛选事实落到 `data-export-case-*` 属性上，产物内脚本按同一口径做纯 DOM 过滤 / 排序：
 * - 关键词 = 名称 / 用例 ID / 描述（与后端 `_match_keyword` 一致）；
 * - 分组 = 分类精确匹配（多选取并集）；标签、评估维度 = 任一命中（与后端 `_match_tags` /
 *   `_match_metrics` 一致）；
 * - 「按评估维度」排序 = 跨资源平均值（与后端 `_sort_by_metric_and_paginate` 同口径）。
 */
import { extractCaseResourceMetrics } from '@/application/report-view/case-matrix'
import type { ReportCaseItem } from '@/domain/models/report'
import { parseMetricKey } from '@/features/report-view/components/case-report-detail/case-report-utils'

/** 用例涉及的评估维度基础名（去掉 `@round:N` / `@overall` 后缀，去重保序） */
export function caseMetricNames(item: ReportCaseItem): string[] {
  const names = new Set<string>()
  const resourceMetrics = extractCaseResourceMetrics(item)
  for (const metrics of Object.values(resourceMetrics)) {
    for (const key of Object.keys(metrics)) {
      const base = parseMetricKey(key).base
      if (base) names.add(base)
    }
  }
  return [...names]
}

/**
 * 每评估维度的跨资源平均值（导出内「按评估维度」排序键）。
 * 与后端一致：同一维度多个资源 / 多个轮次后缀各取一个值再求平均。
 */
export function caseMetricAverages(item: ReportCaseItem): Record<string, number> {
  const sums = new Map<string, { total: number; count: number }>()
  const resourceMetrics = extractCaseResourceMetrics(item)
  for (const metrics of Object.values(resourceMetrics)) {
    for (const [key, rawValue] of Object.entries(metrics)) {
      const value = Number(rawValue)
      if (!Number.isFinite(value)) continue
      const base = parseMetricKey(key).base
      if (!base) continue
      const acc = sums.get(base) ?? { total: 0, count: 0 }
      acc.total += value
      acc.count += 1
      sums.set(base, acc)
    }
  }
  const averages: Record<string, number> = {}
  for (const [name, acc] of sums) averages[name] = acc.total / acc.count
  return averages
}
