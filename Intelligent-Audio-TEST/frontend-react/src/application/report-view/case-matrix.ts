/**
 * 分组/标签对比矩阵重算（application 层，15_报告域.md §3.3.5/3.3.6 平移）。
 * 从用例聚合：{分组|标签 : {资源 : {指标: 平均值, `${指标}_raw`: 原始值集合}}}——
 * 每分组/标签独立平均值（不共用），_raw 供正态分布图（§3.6）。
 */
import type {
  ReportCaseItem,
  ReportMetricConfig,
  MetricMatrix,
  ReportSummary,
} from '@/domain/models/report'

/** 用例指标读取（dict/list 双格式）→ 每资源指标值 */
export function extractCaseResourceMetrics(
  item: ReportCaseItem
): Record<string, Record<string, number>> {
  if (Array.isArray(item.metrics)) {
    const result: Record<string, Record<string, number>> = {}
    for (const group of item.metrics) {
      result[group.resource] = {}
      for (const m of group.metrics ?? []) result[group.resource][m.metric] = m.value
    }
    return result
  }
  return item.metrics
}

/** 每分组/标签独立平均值：MetricAccumulator 累加（sum/count → average，_raw 独立保存） */
export function buildCaseMetricMatrix(
  cases: ReportCaseItem[],
  /** 取分组键：category 或 单个 tag */
  groupKeyOf: (item: ReportCaseItem) => string[],
  allMetrics: ReportMetricConfig[]
): MetricMatrix {
  const matrix: MetricMatrix = {}
  for (const item of cases) {
    const keys = groupKeyOf(item)
    if (keys.length === 0) continue
    const resourceMetrics = extractCaseResourceMetrics(item)
    for (const key of keys) {
      const groupRow = matrix[key] ?? (matrix[key] = {})
      for (const [resource, metrics] of Object.entries(resourceMetrics)) {
        const resourceCol = groupRow[resource] ?? (groupRow[resource] = {})
        for (const metric of allMetrics) {
          const value = metrics[metric.name]
          if (value === undefined) continue
          const averageKey = metric.name
          const rawKey = `${metric.name}_raw`
          const prev = resourceCol[averageKey]
          const prevRaw = Array.isArray(resourceCol[rawKey]) ? (resourceCol[rawKey] as number[]) : []
          const count = (resourceCol[`${metric.name}_count`] as number | undefined) ?? 0
          const sum = (prev as number | undefined) ?? 0
          resourceCol[averageKey] = sum + value
          resourceCol[`${metric.name}_count`] = count + 1
          resourceCol[rawKey] = [...prevRaw, value]
        }
      }
    }
  }
  // 平均 = sum / count（每分组独立）
  for (const groupRow of Object.values(matrix)) {
    for (const resourceCol of Object.values(groupRow)) {
      for (const key of Object.keys(resourceCol)) {
        if (key.endsWith('_count')) {
          const count = resourceCol[key] as number
          const metric = key.replace('_count', '')
          if (count > 0 && typeof resourceCol[metric] === 'number') {
            resourceCol[metric] = (resourceCol[metric] as number) / count
          }
          delete resourceCol[key]
        }
      }
    }
  }
  return matrix
}

/** 矩阵读取：单分组×单资源×单指标（含 _raw 集合） */
export function readMatrixCell(
  matrix: MetricMatrix,
  group: string,
  resource: string,
  metric: string
): { average?: number; raw: number[] } {
  const resourceCol = matrix[group]?.[resource]
  if (!resourceCol) return { raw: [] }
  const raw = Array.isArray(resourceCol[`${metric}_raw`])
    ? (resourceCol[`${metric}_raw`] as number[])
    : []
  const average = typeof resourceCol[metric] === 'number' ? (resourceCol[metric] as number) : undefined
  return { average, raw }
}

/** 资源级原始值集合（raw_data → {metric: values[]}；供矩阵 _raw 合并，§3.6） */
function rawDataForResource(
  summary: ReportSummary,
  resource: string
): Record<string, number[]> {
  const group = summary.raw_data.find((r) => r.resource === resource)
  if (!group) return {}
  const map: Record<string, number[]> = {}
  for (const m of group.metrics) map[m.metric] = m.values
  return map
}

/** 优先级①：按用例标签对比矩阵（§3.3.6）——tag_metric_data 数组行 + raw_data `{metric}_raw` 合并 */
export function buildTagMatrixFromSummary(
  summary: ReportSummary,
  _allMetrics: ReportMetricConfig[]
): MetricMatrix {
  const matrix: MetricMatrix = {}
  for (const group of summary.tag_metric_data) {
    const resource = group.resource
    const rawValues = rawDataForResource(summary, resource)
    for (const tag of group.tags) {
      const row = matrix[tag.tag_name] ?? (matrix[tag.tag_name] = {})
      const col = row[resource] ?? (row[resource] = {})
      for (const m of tag.metrics) {
        col[m.metric] = m.value
        const raw = rawValues[m.metric] ?? []
        if (raw.length > 0) col[`${m.metric}_raw`] = raw
      }
    }
  }
  return matrix
}

/** 优先级①：按用例分组对比矩阵（§3.3.5）——metric_data categories[] 分类聚合 + raw_data 合并 */
export function buildCategoryMatrixFromSummary(
  summary: ReportSummary,
  _allMetrics: ReportMetricConfig[]
): MetricMatrix {
  const matrix: MetricMatrix = {}
  for (const group of summary.metric_data) {
    if (!group.categories?.length) continue
    const resource = group.resource
    const rawValues = rawDataForResource(summary, resource)
    for (const cat of group.categories) {
      const row = matrix[cat.categoryName] ?? (matrix[cat.categoryName] = {})
      const col = row[resource] ?? (row[resource] = {})
      for (const m of cat.metrics) {
        col[m.metric] = m.value
        const raw = rawValues[m.metric] ?? []
        if (raw.length > 0) col[`${m.metric}_raw`] = raw
      }
    }
  }
  return matrix
}
