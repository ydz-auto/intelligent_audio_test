/**
 * 报告摘要归一化工具（application/report-view 层，INT-439 v2.2 平移）。
 * 照现前端 TaskReportPanel/OverviewCard 逻辑：
 *   - getValidResources 六重取值链（resources→devices→apis→summary.resources→summary.apis→summary.devices）
 *   - getNormalizedMetricData 把数组行/旧 dict 统一为 {resource:{metric:value}}
 *   - formatMetricForDisplay 固定 2 位小数（任务级不读 decimal_places，实测注释）
 */
import type {
  ReportMetricConfig,
  ReportResourceHeader,
  ReportSummary,
} from '@/domain/models/report'

/** 资源键 → 资源 header 映射（resourceHeaderMap） */
export function buildResourceHeaderMap(
  summary: ReportSummary | undefined
): Record<string, ReportResourceHeader> {
  const map: Record<string, ReportResourceHeader> = {}
  for (const header of summary?.resource_headers ?? []) {
    map[header.key] = header
    if (header.label) map[header.label] = header
    if (header.name) map[header.name] = header
  }
  return map
}

/** 六重取值链取有效资源键（getValidResources） */
export function getValidResources(summary: ReportSummary | undefined): string[] {
  if (!summary) return []
  const candidates = [
    summary.resources,
    summary.devices?.map((d) => String(d.id)),
    summary.apis?.map((a) => String(a.id)),
    summary.resources,
    summary.apis?.map((a) => a.name),
    summary.devices?.map((d) => d.name),
  ]
  for (const list of candidates) {
    if (list && list.length > 0) return list
  }
  return []
}

/** metric_data（数组行或旧 dict）统一为 {resource:{metric:value}}（getNormalizedMetricData） */
export function getNormalizedMetricData(
  summary: ReportSummary | undefined
): Record<string, Record<string, number>> {
  const result: Record<string, Record<string, number>> = {}
  for (const group of summary?.metric_data ?? []) {
    const metrics: Record<string, number> = {}
    for (const m of group.metrics ?? []) metrics[m.metric] = m.value
    result[group.resource] = metrics
  }
  return result
}

/** 指标值取数（① 设备字符串直查 metricData ② ${id}-${name} ③ 去 ID 前缀名称匹配兜底） */
export function getAverageValue(
  metricName: string,
  resourceKey: string,
  metricData: Record<string, Record<string, number>>
): number | undefined {
  if (metricData[resourceKey]?.[metricName] !== undefined) {
    return metricData[resourceKey][metricName]
  }
  for (const [key, metrics] of Object.entries(metricData)) {
    if (metrics[metricName] === undefined) continue
    if (key === resourceKey) return metrics[metricName]
    const stripped = key.replace(/^(device_|api_|task_)\d+[-_ ]?/, '')
    if (resourceKey.includes(stripped) || stripped.includes(resourceKey)) {
      return metrics[metricName]
    }
  }
  return undefined
}

/** 任务级固定 2 位小数（不读 decimal_places；decimal_places 仅用例卡片用） */
export function formatMetricForDisplay(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

/** 主/子维度分组（all_metrics 按 dimension_type + parent_dimension_name 归组） */
export function groupMetricsByDimension(
  allMetrics: ReportMetricConfig[]
): {
  mainMetrics: ReportMetricConfig[]
  subMetrics: ReportMetricConfig[]
} {
  const main = allMetrics.filter((m) => m.dimension_type !== 'sub')
  const sub = allMetrics.filter((m) => m.dimension_type === 'sub')
  return { mainMetrics: main, subMetrics: sub }
}

/** 指标单位（all_metrics[].unit 兜底 ''） */
export function getMetricUnit(
  allMetrics: ReportMetricConfig[],
  metricName: string
): string {
  return allMetrics.find((m) => m.name === metricName)?.unit ?? ''
}
