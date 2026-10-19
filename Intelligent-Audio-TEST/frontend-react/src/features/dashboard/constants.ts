/**
 * 工作台常量（features/dashboard）：状态/类型/算法中文映射、图表形态与粒度选项。
 * 口径：任务状态枚举原值见 Vue frontend/src/domain/enums.ts（domain 层单一来源）；
 * 徽章配色映射 04_控制台.md §3.7.3 + 09_任务域.md §3.6.1。
 */
import type { StatusVariant } from '@/features/dashboard/components/ui/status-badge'
import type { TrendGranularity } from '@/application/dashboard/use-task-domain-stats'

/** 执行状态 → 中文 + 徽章色（09_任务域.md §3.6.1 映射；后端扩展状态见 Vue domain/enums.ts TaskStatus） */
export const TASK_STATUS_META: Record<string, { label: string; variant: StatusVariant; pulse?: boolean }> = {
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
  // 后端扩展状态（评估相关，Vue domain/enums.ts TaskStatus 实测）
  evaluating: { label: '评估中', variant: 'info' },
  reevaluate_queued: { label: '重新评估排队中', variant: 'info' },
  reevaluating: { label: '重新评估中', variant: 'info', pulse: true },
}

export function getTaskStatusMeta(status: string) {
  return (
    TASK_STATUS_META[status] ?? { label: status, variant: 'neutral' as const }
  )
}

/** 状态键 → 中文名（图表/排行等仅需文案处复用；未知状态原样返回） */
export function getTaskStatusLabel(status: string): string {
  return TASK_STATUS_META[status]?.label ?? status
}

/** 任务类型派生分布 → 中文（04_控制台.md §3.7.2：e2e/api/mixed） */
export const TASK_TYPE_LABELS: Record<string, string> = {
  e2e: '端到端测试',
  api: 'API 测试',
  mixed: '混合',
}

export function getTaskTypeLabel(type: string): string {
  return TASK_TYPE_LABELS[type] ?? type
}

/**
 * 算法类型 → 中文名（mock 占位值，真实枚举随算法域接线对齐）。
 */
export const ALGORITHM_TYPE_LABELS: Record<string, string> = {
  asr_streaming: '流式语音识别',
  wakeword_detect: '唤醒词检测',
  tts_eval: '语音合成评估',
}

export function getAlgorithmTypeLabel(type: string | null): string | null {
  if (!type) return null
  return ALGORITHM_TYPE_LABELS[type] ?? type
}

/** 趋势图粒度选项（task.py granularity 四值实测） */
export const GRANULARITY_OPTIONS: Array<{ value: TrendGranularity; label: string }> = [
  { value: 'day', label: '日' },
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
  { value: 'year', label: '年' },
]

/** 趋势图形态选项（对位 newAPI CONSUMPTION_DISTRIBUTION_CHART_OPTIONS） */
export const TREND_VARIANT_OPTIONS = [
  { value: 'bar', label: '柱状图' },
  { value: 'area', label: '面积图' },
] as const

/** ISO 时间串 → 「YYYY-MM-DD HH:mm」（无 dayjs，轻量格式化；异常原样返回） */
export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}
