/**
 * INT-301：任务级执行/评估双徽章展示口径（单一定义源）。
 *
 * UX 审计 F3：图标映射与徽章样式此前在 TaskCard.ts 与
 * TestExecutionComponent.vue 各存一份，改口径易两处漂移——收敛于此共享模块。
 * 文案继续收敛于 domain/constants/reportLabels.ts（getTaskStatusLabel /
 * getTaskEvaluationStatusLabel）。
 */
import { TaskStatus, TaskEvaluationStatus, ExecutionStatus, EvaluationStatus } from '../domain/enums'
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
 * INT-405：用例级评估徽章文案。用例评估域（EvaluationStatus）比任务评估域
 * （TaskEvaluationStatus）多 queued/running/calculating/stopped 四值，
 * 文案按 status_fields_relationship.md §8.3（负责人裁定 2026-10-15 双徽章口径）。
 * 未知值回退原文容错（后端扩展值不炸界面）。
 */
const caseEvaluationLabelMap: Record<string, string> = {
  [EvaluationStatus.PENDING]: '待评估',
  [EvaluationStatus.QUEUED]: '待评估',
  [EvaluationStatus.RUNNING]: '评估中',
  [EvaluationStatus.CALCULATING]: '计算中',
  [EvaluationStatus.COMPLETED]: '已完成',
  [EvaluationStatus.STOPPED]: '已停止',
  [EvaluationStatus.FAILED]: '评估失败',
}

/** 用例级评估徽章文案（§8.3 口径；未知值回退原文） */
export function getCaseEvaluationStatusText(status: string): string {
  return caseEvaluationLabelMap[status] || status
}

/** 用例级评估徽章图标（与任务级同图标族；queued 待评估/running+calculating 评估进行/stopped 终止） */
export function getCaseEvaluationBadgeIcon(status: string): string {
  const iconMap: Record<string, string> = {
    [EvaluationStatus.PENDING]: 'fa-hourglass-half',
    [EvaluationStatus.QUEUED]: 'fa-hourglass-half',
    [EvaluationStatus.RUNNING]: 'fa-sync-alt fa-spin',
    [EvaluationStatus.CALCULATING]: 'fa-sync-alt fa-spin',
    [EvaluationStatus.COMPLETED]: 'fa-check-circle',
    [EvaluationStatus.STOPPED]: 'fa-stop-circle',
    [EvaluationStatus.FAILED]: 'fa-times-circle',
  }
  return iconMap[status] || 'fa-hourglass-half'
}

/**
 * 执行徽章状态归一（INT-301 F1）：优先取后端派生 executionStatus（评估推进
 * 不落此字段）；缺失（旧数据/回收站轻量行）时回退原始 task.status。
 */
export function getExecutionBadgeStatus(task: { executionStatus?: string; status?: string }): string {
  return task.executionStatus || task.status || TaskStatus.PENDING
}

/**
 * INT-405：用例级执行徽章取值——只读执行维 executionStatus，缺失回退 pending。
 * 不复用 getExecutionBadgeStatus：用例的 status 是后端 derive_task_case_status
 * 复合结果态（含 evaluating 等评估过渡值），回退进执行徽章会串维度。
 */
export function getCaseExecutionBadgeStatus(testCase: { executionStatus?: string }): string {
  return testCase.executionStatus || ExecutionStatus.PENDING
}
