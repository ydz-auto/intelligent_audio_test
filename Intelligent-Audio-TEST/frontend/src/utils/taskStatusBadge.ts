/**
 * INT-301：任务级执行/评估双徽章展示口径（单一定义源）。
 *
 * UX 审计 F3：图标映射与徽章样式此前在 TaskCard.ts 与
 * TestExecutionComponent.vue 各存一份，改口径易两处漂移——收敛于此共享模块。
 * 文案继续收敛于 domain/constants/reportLabels.ts（getTaskStatusLabel /
 * getTaskEvaluationStatusLabel）。
 */
import { TaskStatus, TaskEvaluationStatus, ExecutionStatus } from '../domain/enums'
import { getTaskStatusLabel, getTaskEvaluationStatusLabel } from '../domain/constants/reportLabels'

/** 执行徽章图标（纯执行域，无评估过渡图标） */
export function getExecutionBadgeIcon(status: string): string {
  const iconMap: Record<string, string> = {
    [TaskStatus.PENDING]: 'fa-clock',
    [TaskStatus.QUEUED]: 'fa-hourglass',
    [TaskStatus.RUNNING]: 'fa-spinner fa-spin',
    [ExecutionStatus.COMPLETED]: 'fa-check-circle',
    [ExecutionStatus.FAILED]: 'fa-times-circle',
    [TaskStatus.PAUSED]: 'fa-pause-circle',
    [ExecutionStatus.STOPPED]: 'fa-stop-circle',
    [TaskStatus.SKIPPED]: 'fa-minus-circle',
    [TaskStatus.MERGED]: 'fa-object-group',
  }
  return iconMap[status] || 'fa-clock'
}

/** 执行徽章文案（执行域值走任务状态映射；未知回退原文） */
export function getExecutionStatusText(status: string): string {
  return getTaskStatusLabel(status)
}

/** 评估徽章图标（评估域独立图标族） */
export function getEvaluationBadgeIcon(status: string): string {
  const iconMap: Record<string, string> = {
    [TaskEvaluationStatus.PENDING]: 'fa-hourglass-half',
    [TaskEvaluationStatus.EVALUATING]: 'fa-sync-alt fa-spin',
    [TaskEvaluationStatus.COMPLETED]: 'fa-check-circle',
    [TaskEvaluationStatus.FAILED]: 'fa-times-circle',
    [TaskEvaluationStatus.SKIPPED]: 'fa-forward',
  }
  return iconMap[status] || 'fa-hourglass-half'
}

/** 评估徽章文案（独立口径；未知值回退原文容错） */
export function getEvaluationStatusText(status: string): string {
  return getTaskEvaluationStatusLabel(status)
}

/**
 * 执行徽章状态归一（INT-301 F1）：优先取后端派生 executionStatus（评估推进
 * 不落此字段）；缺失（旧数据/回收站轻量行）时回退原始 task.status。
 */
export function getExecutionBadgeStatus(task: { executionStatus?: string; status?: string }): string {
  return task.executionStatus || task.status || TaskStatus.PENDING
}
