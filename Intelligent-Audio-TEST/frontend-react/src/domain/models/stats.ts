/**
 * 工作台统计域模型（domain 层）——字段逐一对照后端实测 schema：
 * - HomeStatsSummary ← api_gateway/schemas/home.py（HomeStatsDetails 复用 domain/models/home.ts 首页卡同一套）
 * - TaskDomainStats ← api_gateway/schemas/task.py TaskDomainStatsData
 * - TaskQualityStats ← 通过率（task.py TaskStatsData.pass_rate）+ 报告域评估得分聚合口径
 */
/**
 * home.py HomeStatsSummary.device_status：在线/离线计数。
 * （details 侧为含 total 的 DevicesStats，见 ./home；summary 侧仅 online/offline 两字段）
 */
export interface DeviceStatus {
  online: number
  offline: number
}

export interface RecentTaskItem {
  id: number
  name: string
  /** 用例级被测设备类型集合（INT-79 读模型口径） */
  device_types: string[]
  /** 任务状态枚举原值（pending/queued/running/completed/failed/paused/stopped/skipped/merged） */
  status: string
  algorithm_type: string | null
  total_cases: number
  completed_cases: number
  created_at: string | null
}

export interface TopGroupItem {
  id: string
  name: string
  case_count: number
}

/** GET /api/v1/home/stats/summary（home.py HomeStatsSummary） */
export interface HomeStatsSummary {
  recent_tasks: RecentTaskItem[]
  top_groups: TopGroupItem[]
  device_status: DeviceStatus
}

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
