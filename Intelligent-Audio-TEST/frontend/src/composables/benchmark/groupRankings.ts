/**
 * 纯函数：排行行 → (category × metric × scenario) 分组，组内按 rank 升序
 *
 * 分组键对齐后端排行计算语义（功能设计文档 §5.2 / benchmark_ranking_service.py 实测）：
 * - 组 = (category, metric_code, scenario_key)
 * - 组内已按名次排列，前端不改排序（后端 order_by ... rank 实测）
 * - 单主体不归一化时 score100 为空（「—」由展示层兜底）
 */
import type { BenchmarkRankingRow, BenchmarkRankingGroup } from '../../domain/model/benchmark'

/** 分组键分隔符（\u0000 不会出现在枚举/标识值中） */
const KEY_SEPARATOR = '\u0000'

/** 稳定分组：保持 category → metricCode → scenarioKey 字典序，展示顺序可预测 */
export function groupRankings(rows: BenchmarkRankingRow[]): BenchmarkRankingGroup[] {
  const groupMap = new Map<string, BenchmarkRankingGroup>()

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
    // 组内按名次升序（并列名次共享 rank 值，保留接口返回相对顺序）
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

/** 从全量行去重提取测试集清单（排序后，筛选下拉数据源） */
export function extractSuiteOptions(rows: BenchmarkRankingRow[]): string[] {
  const set = new Set(rows.map((r) => r.benchmarkSuite).filter((s) => !!s))
  return [...set].sort()
}

/** 数值缩写（≥1000 显示 1.2K/3.4M，保留两位内），对位 newAPI formatTokens 思路的数值通用版 */
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

/** 计算时间展示（YYYY-MM-DD HH:mm） */
export function formatComputedAt(computedAt: string | null | undefined): string {
  if (!computedAt) return '—'
  const date = new Date(computedAt)
  if (Number.isNaN(date.getTime())) return computedAt
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
