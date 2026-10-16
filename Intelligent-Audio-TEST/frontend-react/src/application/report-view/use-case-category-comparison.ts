/**
 * 按用例分组对比（application 层，15_报告域.md §3.3.5）。
 * 矩阵数据源优先级：① 后端 metric_data/case_categories ② summary.cases 重算
 * （分组取 caseItem.category，缺省「未分类」）。显示类型切换：表格/柱状/折线/雷达/正态分布图。
 */
import { useMemo, useState } from 'react'

import type {
  MetricMatrix,
  ReportDetailData,
  ReportMetricConfig,
} from '@/domain/models/report'
import { buildCaseMetricMatrix, buildCategoryMatrixFromSummary } from './case-matrix'

export type DisplayType = 'table' | 'bar' | 'line' | 'radar' | 'distribution'

export const DISPLAY_TYPE_OPTIONS: { value: DisplayType; label: string }[] = [
  { value: 'table', label: '表格' },
  { value: 'bar', label: '柱状图' },
  { value: 'line', label: '折线图' },
  { value: 'radar', label: '雷达图' },
  { value: 'distribution', label: '正态分布图' },
]

export function useCaseCategoryComparison(report: ReportDetailData) {
  const summary = report.summary
  const allMetrics: ReportMetricConfig[] = summary.all_metrics
  const [activeDisplayType, setActiveDisplayType] = useState<DisplayType>('table')
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [selectedGroups, setSelectedGroups] = useState<string[]>([])
  const [keyword, setKeyword] = useState('')

  const groupKeys = useMemo(
    () => summary.case_categories.map((c) => c.category_name ?? c.category_id ?? ''),
    [summary.case_categories]
  )

  const matrix: MetricMatrix = useMemo(() => {
    // 优先级①：后端 metric_data categories[] 分类聚合（raw_data `{metric}_raw` 合并，§3.6）
    const categoryMatrix = buildCategoryMatrixFromSummary(summary, allMetrics)
    if (Object.keys(categoryMatrix).length > 0) return categoryMatrix
    // 优先级②：summary.cases 重算（分组取 caseItem.category，缺省「未分类」）
    const cases = summary.cases ?? []
    return buildCaseMetricMatrix(
      cases,
      (item) => [item.category ?? '未分类'],
      allMetrics
    )
  }, [summary, allMetrics])

  const filteredGroups = useMemo(() => {
    const all = Object.keys(matrix)
    if (selectedGroups.length > 0) return selectedGroups
    if (keyword) return all.filter((g) => g.includes(keyword))
    return all
  }, [matrix, selectedGroups, keyword])

  const availableMetrics = useMemo(
    () => allMetrics.map((m) => m.name),
    [allMetrics]
  )
  const effectiveMetrics =
    selectedMetrics.length > 0 ? selectedMetrics : availableMetrics

  return {
    groupKeys,
    matrix,
    filteredGroups,
    allMetrics,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    selectedGroups,
    setSelectedGroups,
    keyword,
    setKeyword,
    activeDisplayType,
    setActiveDisplayType,
    effectiveMetrics,
  }
}
