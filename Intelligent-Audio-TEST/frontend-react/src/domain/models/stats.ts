/**
 * 任务域统计模型（domain 层）——字段逐一对照后端实测 schema：
 * - TaskDomainStats ← api_gateway/schemas/task.py TaskDomainStatsData
 * - TaskQualityStats ← 通过率（task.py TaskStatsData.pass_rate）+ 报告域评估得分聚合口径
 * （首页/工作台 HomeStatsDetails·HomeStatsSummary 已迁 domain/models/home.ts，camelCase 域契约）
 */

export interface TrendPoint {
  key: string
  count: number
}

/** GET /api/v1/tasks/stats?granularity=day|week|month|year（task.py TaskDomainStatsData） */
export interface TaskDomainStats {
  total: number
  deleted_total: number
  status_counts: Record<string, number>
  type_counts: Record<string, number>
  trend: TrendPoint[]
  granularity: 'day' | 'week' | 'month' | 'year'
}

/**
 * 质量统计（通过率卡 + 平均得分卡数据源）：
 * pass_rate ← task.py TaskStatsData.pass_rate 实测字段；
 * average_score ← 报告域评估得分聚合口径（evaluation.py ScoreData.score，接口立项前 mock）。
 */
export interface TaskQualityStats {
  pass_rate: number
  average_score: number
  scored_reports: number
}
