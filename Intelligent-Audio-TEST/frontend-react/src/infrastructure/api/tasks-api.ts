/**
 * tasks 域统计 API 桩（infrastructure 层）。
 * TODO(API 接线): 替换为真实请求 ——
 *   GET /api/v1/tasks/stats?granularity=day|week|month|year（task:read，task.py TaskDomainStatsData）
 * 质量统计当前无独立接口：pass_rate 取 task.py TaskStatsData.pass_rate 口径，
 * average_score 为报告域评估得分聚合口径，均返回 mock 常量（红线④）。
 */
import type { TaskDomainStats, TaskQualityStats } from '@/domain/models/stats'

import {
  MOCK_TASK_QUALITY,
  buildMockTaskDomainStats,
} from '../mock/dashboard-mock'

export async function fetchTaskDomainStats(
  granularity: TaskDomainStats['granularity']
): Promise<TaskDomainStats> {
  return buildMockTaskDomainStats(granularity)
}

export async function fetchTaskQualityStats(): Promise<TaskQualityStats> {
  return MOCK_TASK_QUALITY
}
