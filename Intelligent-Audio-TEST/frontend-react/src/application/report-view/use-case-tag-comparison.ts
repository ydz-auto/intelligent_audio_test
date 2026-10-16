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
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [selectedGroups, setSelectedGroups] = useState<string[]>([])

  /** 标签来源合并（updateData 平移：allTags + allCaseTags + tag_metric_data + cases.tags） */
  const allTags = useMemo(() => {
    const map = new Map<string, ReportTag>()
    for (const tag of [...(summary.all_tags ?? []), ...summary.all_case_tags]) {
      const id = tag.tag_id ?? tag.id ?? tag.tag_name
      map.set(id, tag)
    }
    for (const group of summary.tag_metric_data) {
      for (const tag of group.tags) {
        const id = tag.tag_id ?? tag.tag_name
        map.set(id, { tag_id: id, tag_name: tag.tag_name, category_id: tag.category_id, category_name: tag.category_name })
      }
    }
    for (const item of summary.cases ?? []) {
      for (const tagName of item.tags) {
        if (![...map.values()].some((t) => t.tag_name === tagName)) {
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
  }, [summary, allMetrics])

  const filteredTags = useMemo(() => {
    const all = Object.keys(matrix)
    if (selectedTags.length > 0) return selectedTags
    return all
  }, [matrix, selectedTags])

  const availableMetrics = useMemo(
    () => allMetrics.map((m) => m.name),
    [allMetrics]
  )
  const effectiveMetrics =
    selectedMetrics.length > 0 ? selectedMetrics : availableMetrics

  return {
    allTags,
    tagGroups,
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
  }
}
