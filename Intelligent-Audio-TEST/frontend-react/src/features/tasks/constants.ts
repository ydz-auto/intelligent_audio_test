/**
 * 任务域常量（features/tasks，09_任务域.md §9 中文文案 + §3.6.1 双状态映射）。
 * 状态枚举原值见 domain/models/task.ts（domain 层单一来源）。
 */
import type { StatusVariant } from '@/features/dashboard/components/ui/status-badge'

/** 四页签（§3.4；白名单值，路由 /tasks/$tab） */
export const TASKS_TABS = [
  { key: 'daily', label: '日常' },
  { key: 'published', label: '已发布' },
  { key: 'merged', label: '合并' },
  { key: 'cherry-picks', label: '挑选合并' },
] as const

export type TasksTabKey = (typeof TASKS_TABS)[number]['key']

export const TASKS_TAB_WHITELIST: string[] = TASKS_TABS.map((t) => t.key)

/** 执行状态 → 中文 + 徽章色（§3.6.1；对齐工作台 constants.ts TASK_STATUS_META） */
export const EXECUTION_STATUS_META: Record<
  string,
  { label: string; variant: StatusVariant; pulse?: boolean }
> = {
  pending: { label: '待执行', variant: 'neutral' },
  queued: { label: '排队中', variant: 'info' },
  running: { label: '执行中', variant: 'info', pulse: true },
  starting: { label: '启动中', variant: 'info', pulse: true },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '执行失败', variant: 'danger' },
  paused: { label: '已暂停', variant: 'warning' },
  stopped: { label: '已停止', variant: 'neutral' },
  skipped: { label: '已跳过', variant: 'neutral' },
  merged: { label: '已合并', variant: 'purple' },
}

export function getExecutionStatusMeta(status: string | null) {
  if (!status) return { label: '—', variant: 'neutral' as const }
  return (
    EXECUTION_STATUS_META[status] ?? { label: status, variant: 'neutral' as const }
  )
}

/** 评估状态 → 中文 + 徽章色（§3.6.1 评估侧，独立于执行侧） */
export const EVALUATION_STATUS_META: Record<
  string,
  { label: string; variant: StatusVariant; pulse?: boolean }
> = {
  pending: { label: '待评估', variant: 'neutral' },
  evaluating: { label: '评估中', variant: 'info', pulse: true },
  completed: { label: '已评估完成', variant: 'success' },
  failed: { label: '评估失败', variant: 'danger' },
  skipped: { label: '评估跳过', variant: 'neutral' },
}

export function getEvaluationStatusMeta(status: string | null) {
  if (!status) return { label: '—', variant: 'neutral' as const }
  return (
    EVALUATION_STATUS_META[status] ?? {
      label: status,
      variant: 'neutral' as const,
    }
  )
}

/** 任务类型 → 中文（§9：端到端测试/API测试/混合） */
export const TASK_TYPE_LABELS: Record<string, string> = {
  e2e: '端到端测试',
  api: 'API测试',
  mixed: '混合',
}

export function getTaskTypeLabel(type: string | null | undefined): string {
  if (!type) return '—'
  return TASK_TYPE_LABELS[type] ?? type
}

/** 算法类型 → 中文（mock 占位值，真实枚举随算法域接线对齐） */
export const ALGORITHM_TYPE_LABELS: Record<string, string> = {
  asr_streaming: '流式语音识别',
  wakeword_detect: '唤醒词检测',
  tts_eval: '语音合成评估',
}

export function getAlgorithmTypeLabel(type: string | null | undefined): string | null {
  if (!type) return null
  return ALGORITHM_TYPE_LABELS[type] ?? type
}

/** 筛选选项（§3.5 全量中文） */
export const EXECUTION_STATUS_OPTIONS = [
  { value: 'pending', label: '待执行' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '执行失败' },
  { value: 'paused', label: '已暂停' },
  { value: 'stopped', label: '已停止' },
  { value: 'skipped', label: '已跳过' },
  { value: 'merged', label: '已合并' },
]

export const EVALUATION_STATUS_OPTIONS = [
  { value: 'pending', label: '待评估' },
  { value: 'evaluating', label: '评估中' },
  { value: 'completed', label: '已评估完成' },
  { value: 'failed', label: '评估失败' },
  { value: 'skipped', label: '评估跳过' },
]

export const TIME_RANGE_OPTIONS = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

export const PUBLISHED_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'e2e', label: '端到端测试' },
  { value: 'api', label: 'API测试' },
]

export const PUBLISHED_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'published', label: '已发布' },
  { value: 'archived', label: '已归档' },
]

export const MERGE_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'merged', label: '已合并' },
  { value: 'completed', label: '已完成' },
]

/** 任务标签集合（facet 多选数据源；真实接线为现列表标签去重集合） */
export const TASK_TAG_OPTIONS = ['旗舰回归', '远场', '车载', '唤醒词', '压测', 'API', '耳机', '夜间', '播报音质', '方言', '抽样', '主观评估']

/** 统计徽章行（§3.5：7 枚，色条语义） */
export const STATS_BADGES: Array<{
  key: string
  label: string
  colorClass: string
}> = [
  { key: 'total', label: '总任务', colorClass: 'bg-neutral' },
  { key: 'pending', label: '待执行', colorClass: 'bg-warning' },
  { key: 'queued', label: '排队中', colorClass: 'bg-warning' },
  { key: 'running', label: '执行中', colorClass: 'bg-info' },
  { key: 'completed', label: '已完成', colorClass: 'bg-success' },
  { key: 'failed', label: '执行失败', colorClass: 'bg-destructive' },
  { key: 'deleted', label: '已删除', colorClass: 'bg-neutral' },
]

/** 已发布任务行内高频动作（§3.7）权限码 */
export const PUBLISHED_ROW_ACTIONS = [
  { key: 'execute', label: '执行', permission: 'published_task:execute' },
  { key: 'version', label: '版本', permission: 'published_task:read' },
  { key: 'new-version', label: '新版本', permission: 'published_task:version' },
  { key: 'rename', label: '重命名', permission: 'published_task:read' },
  { key: 'archive', label: '归档', permission: 'published_task:archive' },
] as const

/** ISO 时间串 → 「YYYY-MM-DD HH:mm」（轻量格式化，无 dayjs；异常原样返回） */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}

/** 时长 ms → 「x 秒 / x 分钟」 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.round(seconds / 60)} 分钟`
}
