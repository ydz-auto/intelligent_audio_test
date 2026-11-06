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
  // 表单草稿态（筛选卡绑定；「应用筛选」提交后才生效）
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [selectedGroups, setSelectedGroups] = useState<string[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [keyword, setKeyword] = useState('')
  // 已应用态（驱动结果）
  const [appliedMetrics, setAppliedMetrics] = useState<string[]>([])
  const [appliedGroups, setAppliedGroups] = useState<string[]>([])
  const [appliedTags, setAppliedTags] = useState<string[]>([])
  const [appliedKeyword, setAppliedKeyword] = useState('')

  const groupKeys = useMemo(
    () => summary.case_categories.map((c) => c.category_name ?? c.category_id ?? ''),
    [summary.case_categories]
  )

  /** 全量标签（all_case_tags[含分类] + all_tags 兼容旧名 + tag_metric_data 提取；去重） */
  const allTags = useMemo(() => {
    const set = new Set<string>()
    for (const t of summary.all_case_tags ?? []) set.add(t.tag_name)
    for (const t of summary.all_tags ?? []) set.add(t.tag_name)
    for (const group of summary.tag_metric_data) {
      for (const tag of group.tags) set.add(tag.tag_name)
    }
    return [...set]
  }, [summary])

  const matrix: MetricMatrix = useMemo(() => {
    // 标签筛选激活：从 summary.cases 按标签过滤后按分组重算（§3.3.5 筛选卡「用例标签多选」）
    if (appliedTags.length > 0) {
      const filteredCases = (summary.cases ?? []).filter((item) =>
        item.tags.some((t) => appliedTags.includes(t))
      )
      return buildCaseMetricMatrix(
        filteredCases,
        (item) => [item.category ?? '未分类'],
        allMetrics
      )
    }
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
  }, [summary, allMetrics, appliedTags])

  const filteredGroups = useMemo(() => {
    const all = Object.keys(matrix)
    if (appliedGroups.length > 0) return appliedGroups
    if (appliedKeyword) return all.filter((g) => g.includes(appliedKeyword))
    return all
  }, [matrix, appliedGroups, appliedKeyword])

  const availableMetrics = useMemo(
    () => allMetrics.map((m) => m.name),
    [allMetrics]
  )
  const effectiveMetrics =
    appliedMetrics.length > 0 ? appliedMetrics : availableMetrics

  /** 「应用筛选」：把表单草稿提交为生效条件（跳过防抖，立即生效） */
  const applyFilters = () => {
    setAppliedKeyword(keyword)
    setAppliedGroups(selectedGroups)
    setAppliedTags(selectedTags)
    setAppliedMetrics(selectedMetrics)
  }

  /** 「重置」：清空草稿与已应用条件 */
  const resetFilters = () => {
    setKeyword('')
    setSelectedGroups([])
    setSelectedTags([])
    setSelectedMetrics([])
    setAppliedKeyword('')
    setAppliedGroups([])
    setAppliedTags([])
    setAppliedMetrics([])
  }

  return {
    groupKeys,
    allTags,
    matrix,
    filteredGroups,
    allMetrics,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    selectedGroups,
    setSelectedGroups,
    selectedTags,
    setSelectedTags,
    keyword,
    setKeyword,
    activeDisplayType,
    setActiveDisplayType,
    effectiveMetrics,
    applyFilters,
    resetFilters,
  }
}
