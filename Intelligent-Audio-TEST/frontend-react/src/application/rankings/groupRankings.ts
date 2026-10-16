/**
 * 排行榜分组纯函数（application 层，零 UI 依赖，配 vitest 单测）。
 * 分组键：(metricCode × scenarioKey)——category 由页签锁定，组内 rank 升序
 * （后端已按 rank 排序返回，本函数仅保证组内序与并列名次语义）。
 * 边界：并列名次共享 rank / 单主体不归一化 score100 为空 / 场景缺省「通用」。
 */
import type { RankingGroup, RankingRow } from '@/domain/models/benchmark'

/** 场景缺省值（Config.BENCHMARK_DEFAULT_SCENARIO 实测「通用」） */
export const DEFAULT_SCENARIO_KEY = '通用'

/**
 * rows → (metricCode × scenarioKey) 指标组；返回组内 rank 升序。
 * 分组时忽略空行；组间顺序按首次出现保持稳定。
 */
export function groupRankings(rows: RankingRow[]): RankingGroup[] {
  const groupsByKey = new Map<string, RankingGroup>()

  for (const row of rows) {
    const scenarioKey = row.scenarioKey || DEFAULT_SCENARIO_KEY
    const key = `${row.metricCode}\u0000${scenarioKey}`
    let group = groupsByKey.get(key)
    if (!group) {
      group = {
        metricCode: row.metricCode,
        metricName: row.metricName,
        unit: row.unit,
        direction: row.direction,
        category: row.category,
        scenarioKey,
        total: row.total,
        rows: [],
        computedAt: row.computedAt,
      }
      groupsByKey.set(key, group)
    }
    group.rows.push(row)
  }

  const groups = [...groupsByKey.values()]
  for (const group of groups) {
    group.rows.sort((a, b) => a.rank - b.rank)
  }
  return groups
}
