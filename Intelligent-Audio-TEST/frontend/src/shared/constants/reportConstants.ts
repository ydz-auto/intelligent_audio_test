export const TASK_STATUS_MAP: Record<string, string> = {
  'pending': '待执行',
  'running': '执行中',
  'completed': '已完成',
  'failed': '执行失败',
  'paused': '已暂停',
  'stopped': '已停止',
  'queued': '排队中',
  'skipped': '已跳过',
  'merged': '已合并',
  'evaluating': '评估中',
  'reevaluate_queued': '重新评估排队中',
  'reevaluating': '重新评估中'
} as const;

export const REPORT_TYPE_MAP: Record<string, string> = {
  'task': '任务报告',
  'comparison': '对比报告',
  'secondaryComparison': '二次对比报告',
  'secondary_comparison': '二次对比报告',
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
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' }
] as const;

export const REPORT_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '发布' }
] as const;

/**
 * 历史报告页视图 Tab 枚举。
 * 与后端列表接口的 type / status 过滤参数一一对应（配置化、避免魔法字符串）。
 */
export const REPORT_TABS = {
  ALL: 'all',
  DRAFT: 'draft',
  PUBLISHED: 'published',
  COMPARISON: 'comparison'
} as const;

export type ReportTabValue = (typeof REPORT_TABS)[keyof typeof REPORT_TABS];

export interface ReportTabOption {
  value: ReportTabValue;
  label: string;
  icon: string;
}

export const REPORT_TAB_OPTIONS: ReadonlyArray<ReportTabOption> = [
  { value: REPORT_TABS.ALL, label: '全部报告', icon: 'fas fa-layer-group' },
  { value: REPORT_TABS.DRAFT, label: '草稿报告', icon: 'fas fa-edit' },
  { value: REPORT_TABS.PUBLISHED, label: '发布报告', icon: 'fas fa-check-circle' },
  { value: REPORT_TABS.COMPARISON, label: '对比报告', icon: 'fas fa-exchange-alt' }
];

/** 归类为「对比报告」视图的报告类型集合（兼容新旧命名，用于客户端归类展示） */
const COMPARISON_REPORT_TYPES: readonly string[] = [
  'comparison',
  'secondaryComparison',
  'secondary_comparison'
];

/** 后端 /reports 列表接口支持的多类型过滤值（对比报告视图 Tab 查询使用，与后端枚举一致） */
export const COMPARISON_REPORT_TYPE_QUERY: readonly string[] = [
  'comparison',
  'secondary_comparison'
];

export function isComparisonReportType(type: string): boolean {
  return COMPARISON_REPORT_TYPES.includes(type);
}
