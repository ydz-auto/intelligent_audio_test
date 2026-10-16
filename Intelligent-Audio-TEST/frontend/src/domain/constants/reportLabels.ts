import { TaskStatus, ReportStatus, ViewMode, TaskEvaluationStatus } from '@/domain/enums';

export const TASK_STATUS_MAP: Record<string, string> = {
  [TaskStatus.PENDING]: '待执行',
  [TaskStatus.RUNNING]: '执行中',
  [TaskStatus.COMPLETED]: '已完成',
  [TaskStatus.FAILED]: '执行失败',
  [TaskStatus.PAUSED]: '已暂停',
  [TaskStatus.STOPPED]: '已停止',
  [TaskStatus.QUEUED]: '排队中',
  [TaskStatus.SKIPPED]: '已跳过',
  [TaskStatus.MERGED]: '已合并',
  [TaskStatus.EVALUATING]: '评估中',
  [TaskStatus.REEVALUATE_QUEUED]: '重新评估排队中',
  [TaskStatus.REEVALUATING]: '重新评估中'
} as const;

/**
 * INT-301：任务级评估状态文案（独立于执行状态徽章的展示口径）。
 * completed 在评估侧与执行侧均呈现「已完成」，以徽章分组/图标/配色区分。
 */
export const TASK_EVALUATION_STATUS_MAP: Record<string, string> = {
  [TaskEvaluationStatus.PENDING]: '待评估',
  [TaskEvaluationStatus.EVALUATING]: '评估中',
  [TaskEvaluationStatus.COMPLETED]: '已完成',
  [TaskEvaluationStatus.FAILED]: '评估失败',
  [TaskEvaluationStatus.SKIPPED]: '评估跳过'
} as const;

export const REPORT_TYPE_MAP: Record<string, string> = {
  'task': '任务报告',
  'comparison': '对比报告',
  'secondary_comparison': '二次对比报告',
  'secondaryComparison': '二次对比报告',
  'secondary': '二次对比报告',
  'benchmark': 'Benchmark 报告'
} as const;

export const REPORT_STATUS_MAP: Record<string, string> = {
  [ReportStatus.DRAFT]: '草稿',
  [ReportStatus.PUBLISHED]: '已发布',
  [ReportStatus.FINAL]: '最终版'
} as const;

export type TaskStatusKey = keyof typeof TASK_STATUS_MAP;
export type ReportTypeKey = keyof typeof REPORT_TYPE_MAP;
export type ReportStatusKey = keyof typeof REPORT_STATUS_MAP;

export function getTaskStatusLabel(status: string): string {
  return TASK_STATUS_MAP[status] || status;
}

/** INT-301：任务级评估状态文案（未知值回退原文，容错后端扩展） */
export function getTaskEvaluationStatusLabel(status: string): string {
  return TASK_EVALUATION_STATUS_MAP[status] || status;
}

export function getReportTypeLabel(type: string): string {
  return REPORT_TYPE_MAP[type] || type;
}

export function getReportStatusLabel(status: string): string {
  return REPORT_STATUS_MAP[status] || status;
}

export const TIME_RANGE_OPTIONS = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' }
] as const;

export const REPORT_STATUS_OPTIONS = [
  { value: ViewMode.ALL, label: '全部状态' },
  { value: ReportStatus.DRAFT, label: '草稿' },
  { value: ReportStatus.PUBLISHED, label: '发布' }
] as const;
