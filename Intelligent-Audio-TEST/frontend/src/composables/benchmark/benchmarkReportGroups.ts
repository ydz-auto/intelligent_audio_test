/**
 * 纯函数：Benchmark 报告排行快照行 → (category × metric × scenario) 分组（INT-483）
 *
 * 分组键对齐后端排行计算语义（功能设计文档 §5.2 / benchmark_ranking_service.py 实测）：
 * - 组 = (category, metric_code, scenario_key)，组内已按名次排列（后端 order_by ... rank）
 * - 与 INT-482 排行页 groupRankings 同构，独立成源避免跨分支依赖（快照行类型自含）
 */
import type {
  BenchmarkSnapshotRow,
  BenchmarkReportDirectionType,
} from '../../domain/model/benchmarkReport'
import { BenchmarkReportDirectionLabels } from '../../domain/model/benchmarkReport'

/** 分组键分隔符（\u0000 不会出现在枚举/标识值中） */
const KEY_SEPARATOR = '\u0000'

/** 排行快照指标组（category × metricCode × scenarioKey 一组） */
export interface BenchmarkSnapshotGroup {
  category: string
  metricCode: string
  metricName: string
  scenarioKey: string
  unit: string
  direction: BenchmarkReportDirectionType | (string & {})
  computedAt: string | null
  total: number
  rows: BenchmarkSnapshotRow[]
}

/** 稳定分组：保持 category → metricCode → scenarioKey 字典序，展示顺序可预测 */
export function groupSnapshotRows(rows: BenchmarkSnapshotRow[]): BenchmarkSnapshotGroup[] {
  const groupMap = new Map<string, BenchmarkSnapshotGroup>()

  for (const row of rows) {
    const key = `${row.category}${KEY_SEPARATOR}${row.metricCode}${KEY_SEPARATOR}${row.scenarioKey}`
    let group = groupMap.get(key)
    if (!group) {
      group = {
        category: row.category,
        metricCode: row.metricCode,
        metricName: row.metricName,
        scenarioKey: row.scenarioKey,
        unit: row.unit,
        direction: row.direction,
        computedAt: row.computedAt,
        total: 0,
        rows: [],
      }
      groupMap.set(key, group)
    }
    group.rows.push(row)
  }

  const groups = [...groupMap.values()]
  for (const group of groups) {
    group.rows.sort((a, b) => a.rank - b.rank)
    group.total = group.rows.length
    const computedTimes = group.rows.map((r) => r.computedAt).filter((t): t is string => !!t)
    group.computedAt = computedTimes.length ? computedTimes[0] : null
  }

  groups.sort(
    (a, b) =>
      a.category.localeCompare(b.category) ||
      a.metricCode.localeCompare(b.metricCode) ||
      a.scenarioKey.localeCompare(b.scenarioKey),
  )

  return groups
}

/** 排行方向标签（未知值回退原文，容错后端扩展） */
export function directionLabel(direction: string): string {
  return BenchmarkReportDirectionLabels[direction as keyof typeof BenchmarkReportDirectionLabels] || direction
}

/** 数值缩写（≥1000 显示 1.2K/3.4M，保留两位内） */
export function formatMetricValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1_000_000) {
    return `${trimTrailingZero(value / 1_000_000)}M`
  }
  if (abs >= 1_000) {
    return `${trimTrailingZero(value / 1_000)}K`
  }
  return trimTrailingZero(value)
}

function trimTrailingZero(value: number): string {
  const fixed = value.toFixed(2)
  return fixed.replace(/\.?0+$/, '')
}
