/**
 * 日志查看页常量（features/logs；17_配置运维.md §4）。
 * 级别/标记色映射与分页口径；筛选 sentinel 'all' 与 07 配置运维 Vue 一致。
 */
import type { StatusVariant } from '@/features/dashboard/components/ui/status-badge'

export const LOG_SEARCH_DEBOUNCE_MS = 300
export const DEFAULT_PAGE_SIZE = 20
export const PAGE_SIZE_OPTIONS = [10, 20, 30, 50, 100]

/** 筛选「全部」sentinel（分类/模块/标记/算法 Select；发后端时由 adapter 剔除） */
export const FILTER_ALL = 'all'

/** 级别 → StatusBadge variant + 行染 tint（§4.4：ERROR/CRITICAL=destructive + rose tint） */
export const LOG_LEVEL_META: Record<
  string,
  { label: string; variant: StatusVariant; tint?: string }
> = {
  DEBUG: { label: 'DEBUG', variant: 'neutral' },
  INFO: { label: 'INFO', variant: 'info' },
  WARNING: { label: 'WARNING', variant: 'warning' },
  ERROR: { label: 'ERROR', variant: 'danger', tint: 'bg-rose-50/40 dark:bg-rose-950/20' },
  CRITICAL: { label: 'CRITICAL', variant: 'danger', tint: 'bg-rose-50/40 dark:bg-rose-950/20' },
}

/** 标记颜色 → 行首色条/色点（§4.4 marked 行 border-l-4；§4.5 批量标记色） */
export const LOG_MARK_META: Record<
  string,
  { label: string; barClass: string; dotClass: string }
> = {
  yellow: { label: '黄色', barClass: 'border-l-yellow-400', dotClass: 'bg-yellow-400' },
  red: { label: '红色', barClass: 'border-l-destructive', dotClass: 'bg-destructive' },
  green: { label: '绿色', barClass: 'border-l-success', dotClass: 'bg-success' },
  blue: { label: '蓝色', barClass: 'border-l-sky-500', dotClass: 'bg-sky-500' },
}

/** 实时监控轮询退避（对照 Vue logView.ts REALTIME_POLL_BASE/IDLE_MAX） */
export const REALTIME_POLL_BASE_INTERVAL_MS = 5000
export const REALTIME_POLL_IDLE_MAX_MS = 30_000
/** WS 连接超时判定（超过视为不可用，降级轮询） */
export const REALTIME_WS_CONNECT_TIMEOUT_MS = 4000

/** 日志时间格式化（对照 Vue formatLogTime：合法日期 toLocaleString，非法原样） */
export function formatLogTime(raw: string | undefined | null): string {
  const rawTime = raw ?? ''
  if (!rawTime) return ''
  const date = new Date(rawTime)
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleString('zh-CN', { hour12: false })
  }
  return rawTime
}
