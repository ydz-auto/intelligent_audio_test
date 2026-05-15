export const TASK_STATUS_MAP: Record<string, string> = {
  'pending': '待执行',
  'running': '执行中',
  'completed': '已完成',
  'failed': '执行失败',
  'paused': '已暂停',
  'stopped': '已停止',
  'queued': '排队中',
  'skipped': '已跳过',
  'merged': '已合并'
} as const;

export const REPORT_TYPE_MAP: Record<string, string> = {
  'task': '任务报告',
  'comparison': '对比报告',
  'secondaryComparison': '二次对比报告',
  'secondary': '二次对比报告'
} as const;

export const REPORT_STATUS_MAP: Record<string, string> = {
  'draft': '草稿',
  'published': '已发布',
  'final': '最终版'
} as const;

export type TaskStatusKey = keyof typeof TASK_STATUS_MAP;
export type ReportTypeKey = keyof typeof REPORT_TYPE_MAP;
export type ReportStatusKey = keyof typeof REPORT_STATUS_MAP;

export function getTaskStatusLabel(status: string): string {
  return TASK_STATUS_MAP[status] || status;
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

export const REPORT_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'comparison', label: '对比报告' },
  { value: 'secondaryComparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' }
] as const;

export const REPORT_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '发布' }
] as const;
