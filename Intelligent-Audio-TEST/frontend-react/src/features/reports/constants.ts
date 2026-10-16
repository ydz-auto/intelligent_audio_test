/**
 * 报告中心常量（interfaces/features/reports 层，§3/§8 文案与枚举中文源）。
 * 枚举口径对照 api_gateway/schemas/report.py（ReportType/ReportStatus）与
 * schemas/algorithm.py（algorithm_type 名）；中文映射为规范 §8 定稿文案。
 */
import type {
  ReportSortBy,
  ReportStatus,
  ReportTimeRange,
  ReportType,
  ReportViewMode,
} from '@/domain/models/report'
import type { StatusVariant } from '@/features/dashboard/components/ui/status-badge'

export const REPORT_TYPE_OPTIONS: {
  value: ReportType | 'all'
  label: string
}[] = [
  { value: 'all', label: '全部' },
  { value: 'task', label: '任务报告' },
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'benchmark', label: 'Benchmark 报告' },
]

export const REPORT_STATUS_OPTIONS: {
  value: ReportStatus | 'all'
  label: string
}[] = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '已发布' },
]

export const TIME_RANGE_OPTIONS: {
  value: ReportTimeRange | 'all'
  label: string
}[] = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

export const REPORT_SORT_OPTIONS: {
  value: ReportSortBy
  label: string
}[] = [
  { value: 'created_at', label: '创建时间' },
  { value: 'name', label: '报告名称' },
  { value: 'pass_rate', label: '通过率' },
  { value: 'total_cases', label: '用例数' },
]

export const REPORT_VIEW_MODES: { value: ReportViewMode; label: string }[] = [
  { value: 'table', label: '表格' },
  { value: 'card', label: '卡片' },
]

export const REPORT_TYPE_META: Record<
  ReportType,
  { label: string; variant: StatusVariant }
> = {
  task: { label: '任务报告', variant: 'neutral' },
  comparison: { label: '对比报告', variant: 'info' },
  secondary_comparison: { label: '二次对比', variant: 'purple' },
  benchmark: { label: 'Benchmark 报告', variant: 'info' },
}

export const REPORT_STATUS_META: Record<
  ReportStatus,
  { label: string; variant: StatusVariant }
> = {
  draft: { label: '草稿', variant: 'warning' },
  published: { label: '已发布', variant: 'success' },
}

/** 算法类型中文映射（对照 schemas/algorithm.py 实测枚举名；未知回退原值） */
export const ALGORITHM_LABELS: Record<string, string> = {
  asr_streaming: '流式识别',
  asr_offline: '离线识别',
  wakeword_detect: '唤醒检测',
  tts_eval: 'TTS 评估',
  spl_eval: 'SPL 评估',
}

export function getAlgorithmLabel(algorithmType?: string): string {
  if (!algorithmType) return '—'
  return ALGORITHM_LABELS[algorithmType] ?? algorithmType
}

/** 通过率语义色（规范 §5 / V9.7.31 基线：≥80 success / ≥50 warning / 其余 danger） */
export function getSuccessRateVariant(rate: number): 'success' | 'warning' | 'danger' {
  if (rate >= 80) return 'success'
  if (rate >= 50) return 'warning'
  return 'danger'
}

/** 用例整体状态语义色（§4.7：pass/danger 指示点） */
export const CASE_STATUS_META: Record<
  string,
  { label: string; variant: StatusVariant }
> = {
  pass: { label: '通过', variant: 'success' },
  fail: { label: '失败', variant: 'danger' },
  skip: { label: '跳过', variant: 'neutral' },
  unknown: { label: '未知', variant: 'neutral' },
}

export function formatDateTime(value?: string): string {
  if (!value) return '—'
  // 入参形态：'2026-10-15T09:20:00'（schema created_at 实测）→ 'YYYY-MM-DD HH:mm'
  const normalized = value.includes('T') ? value.replace('T', ' ') : value
  return normalized.length > 16 ? normalized.slice(0, 16) : normalized
}

/** 排序下拉当前项中文标签 */
export function getReportSortLabel(sortBy: ReportSortBy): string {
  return REPORT_SORT_OPTIONS.find((o) => o.value === sortBy)?.label ?? '创建时间'
}
