/**
 * tasks 域统计 API（infrastructure/api 层，接线基座 INT-605 client.ts 出口）。
 *   GET /api/v1/tasks/stats?granularity=day|week|month|year（task:read，task.py TaskDomainStatsData）
 * 质量统计无独立接口：pass_rate 以任务域 status_counts 派生（completed/total，对齐
 * task.py TaskStatsData.pass_rate 口径）；average_score/scored_reports 为报告域评估得分
 * 聚合，后端尚无对应端点 —— 返回 0 并在 FEAT 卡留证据（INT-638 接线评论）。
 */
import { request } from '@/infrastructure/api/client'
import type { TaskDomainStats, TaskQualityStats } from '@/domain/models/stats'
import type { TaskDomainStatsDto } from '@/infrastructure/dto/task.dto'

/** GET /api/v1/tasks/stats?granularity=day|week|month|year（任务域全量聚合统计） */
export async function fetchTaskDomainStats(
  granularity: TaskDomainStats['granularity']
): Promise<TaskDomainStats> {
  const dto = await request<TaskDomainStatsDto>('GET', '/tasks/stats', undefined, {
    params: { granularity },
  })
  return {
    total: dto.total ?? 0,
    deleted_total: dto.deleted_total ?? 0,
    status_counts: dto.status_counts ?? {},
    type_counts: dto.type_counts ?? { api: 0, e2e: 0, mixed: 0 },
    trend: dto.trend ?? [],
    granularity: (dto.granularity as TaskDomainStats['granularity']) ?? granularity,
  }
}

/**
 * 任务质量统计（无独立端点）：pass_rate 以 /tasks/stats status_counts 派生
 * （completed/total，缺 completed 时以 total-failed-pending-… 兜底）；
 * average_score/scored_reports 报告域聚合后端未落 → 0（FEAT 证据见 INT-638）。
 */
export async function fetchTaskQualityStats(): Promise<TaskQualityStats> {
  const dto = await request<TaskDomainStatsDto>('GET', '/tasks/stats', undefined, {
    params: { granularity: 'day' },
  })
  const status = dto.status_counts ?? {}
  const total = dto.total ?? 0
  const completed = status.completed ?? 0
  const passRate = total > 0 ? Math.round((completed / total) * 1000) / 10 : 0
  return {
    pass_rate: passRate,
    average_score: 0,
    scored_reports: 0,
  }
}
