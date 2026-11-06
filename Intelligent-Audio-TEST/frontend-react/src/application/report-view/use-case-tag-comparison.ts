/**
 * 按用例标签对比（application 层，15_报告域.md §3.3.6）。
 * 标签来源合并：summary.allCaseTags + all_tags + tag_metric_data 提取 + cases 标签；
 * 存在未打标签用例补「未标记」。每标签独立平均值（不共用，_raw 独立保存）。
 * 标签带分类（category_id/category_name）——筛选器按分类分组展示（§3.6）。
 */
import { useMemo, useState } from 'react'

import type {
  MetricMatrix,
  ReportDetailData,
  ReportMetricConfig,
  ReportTag,
} from '@/domain/models/report'
import { buildCaseMetricMatrix, buildTagMatrixFromSummary } from './case-matrix'
import type { DisplayType } from './use-case-category-comparison'

export { DISPLAY_TYPE_OPTIONS } from './use-case-category-comparison'
export type { DisplayType }

export function useCaseTagComparison(report: ReportDetailData) {
  const summary = report.summary
  const allMetrics: ReportMetricConfig[] = summary.all_metrics
  const [activeDisplayType, setActiveDisplayType] = useState<DisplayType>('table')
  // 表单草稿态（筛选卡绑定；「应用筛选」提交后才生效）
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [selectedGroups, setSelectedGroups] = useState<string[]>([])
  // 已应用态（驱动结果）
  const [appliedMetrics, setAppliedMetrics] = useState<string[]>([])
  const [appliedTags, setAppliedTags] = useState<string[]>([])
  const [appliedGroups, setAppliedGroups] = useState<string[]>([])

  const groupKeys = useMemo(
    () => summary.case_categories.map((c) => c.category_name ?? c.category_id ?? ''),
    [summary.case_categories]
  )

  /** 标签来源合并（updateData 平移：allTags + allCaseTags + tag_metric_data + cases.tags） */
  const allTags = useMemo(() => {
    const map = new Map<string, ReportTag>()
    const put = (tag: ReportTag) => {
      // 真实库存在 tag_name 为空的聚合行（报告 395 tag_metric_data 实测）：空名标签跳过
      if (!tag.tag_name || !String(tag.tag_name).trim()) return
      const id = tag.tag_id ?? tag.id ?? tag.tag_name
      map.set(String(id), tag)
    }
    for (const tag of [...(summary.all_tags ?? []), ...summary.all_case_tags]) put(tag)
    for (const group of summary.tag_metric_data) {
      for (const tag of group.tags) {
        put({ tag_id: tag.tag_id ?? tag.tag_name, tag_name: tag.tag_name, category_id: tag.category_id, category_name: tag.category_name })
      }
    }
    for (const item of summary.cases ?? []) {
      for (const tagName of item.tags) {
        if (tagName && ![...map.values()].some((t) => t.tag_name === tagName)) {
          map.set(tagName, { tag_name: tagName })
        }
      }
    }
    return [...map.values()]
  }, [summary.all_tags, summary.all_case_tags, summary.tag_metric_data, summary.cases])

  /** 标签按分类分组（分类组头 + 组内标签；无分类入「其他」） */
  const tagGroups = useMemo(() => {
    const map = new Map<string, ReportTag[]>()
    for (const tag of allTags) {
      const cat = tag.category_name ?? '其他'
      const list = map.get(cat) ?? []
      list.push(tag)
      map.set(cat, list)
    }
    return [...map.entries()]
  }, [allTags])

  const matrix: MetricMatrix = useMemo(() => {
    // 分组筛选激活：从 summary.cases 按分组过滤后按标签重算（§3.3.6 筛选卡「用例分组多选」）
    if (appliedGroups.length > 0) {
      const filteredCases = (summary.cases ?? []).filter(
        (item) => item.category && appliedGroups.includes(item.category)
      )
      const tagged = filteredCases.filter((c) => c.tags.length > 0)
      const untagged = filteredCases.filter((c) => c.tags.length === 0)
      const rebuilt = buildCaseMetricMatrix(tagged, (item) => item.tags, allMetrics)
      if (untagged.length > 0) {
        Object.assign(rebuilt, buildCaseMetricMatrix(untagged, () => ['未标记'], allMetrics))
      }
      return rebuilt
    }
    // 优先级①：后端 tag_metric_data（per-resource × tag，raw_data `{metric}_raw` 合并，§3.6）
    const tagMatrix = buildTagMatrixFromSummary(summary, allMetrics)
    if (Object.keys(tagMatrix).length > 0) return tagMatrix
    // 优先级②：summary.cases 重算
    const cases = summary.cases ?? []
    const untagged = cases.filter((c) => c.tags.length === 0)
    const tagged = cases.filter((c) => c.tags.length > 0)
    const matrix = buildCaseMetricMatrix(tagged, (item) => item.tags, allMetrics)
    if (untagged.length > 0) {
      const fallback = buildCaseMetricMatrix(untagged, () => ['未标记'], allMetrics)
      Object.assign(matrix, fallback)
    }
    return matrix
  }, [summary, allMetrics, appliedGroups])

  const filteredTags = useMemo(() => {
    const all = Object.keys(matrix)
    if (appliedTags.length > 0) return appliedTags
    return all
  }, [matrix, appliedTags])

  const availableMetrics = useMemo(
    () => allMetrics.map((m) => m.name),
    [allMetrics]
  )
  const effectiveMetrics =
    appliedMetrics.length > 0 ? appliedMetrics : availableMetrics

  /** 「应用筛选」：把表单草稿提交为生效条件（立即生效） */
  const applyFilters = () => {
    setAppliedTags(selectedTags)
    setAppliedGroups(selectedGroups)
    setAppliedMetrics(selectedMetrics)
  }

  /** 「重置」：清空草稿与已应用条件 */
  const resetFilters = () => {
    setSelectedTags([])
    setSelectedGroups([])
    setSelectedMetrics([])
    setAppliedTags([])
    setAppliedGroups([])
    setAppliedMetrics([])
  }

  return {
    allTags,
    tagGroups,
    groupKeys,
    matrix,
    filteredTags,
    allMetrics,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    selectedTags,
    setSelectedTags,
    selectedGroups,
    setSelectedGroups,
    activeDisplayType,
    setActiveDisplayType,
    effectiveMetrics,
    applyFilters,
    resetFilters,
  }
}
