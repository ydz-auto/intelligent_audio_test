/**
 * 任务域时间展示工具（features/tasks/lib；页面不再各自切片）。
 *
 * 后端下发的时间串多为无时区后缀的裸 UTC（如 `2026-10-23T05:11:14.017258`，
 * task.py 实测），直接 `T→空格` + `slice` 会原样显示 UTC，比本地（Asia/Shanghai）
 * 早 8 小时。此处统一按 UTC 解析后转本地时区输出「YYYY-MM-DD HH:mm(:ss)」。
 * 带时区后缀（`Z` / `±HH:mm`）的串按原语义解析。
 */
import type { TaskDetailData } from '@/domain/models/task'

/** 无时区后缀的日期时间串（日期 + T/空格 + 时分[秒[.毫秒]]） */
const NAIVE_DATETIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)$/

/** 后端时间串 → Date（无时区后缀按 UTC 解释）；空值 / 不可解析 → null */
export function parseApiDateTime(
  value: string | null | undefined
): Date | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  const naive = NAIVE_DATETIME.exec(trimmed)
  const normalized = naive ? `${naive[1]}T${naive[2]}Z` : trimmed
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** Date → 本地「YYYY-MM-DD HH:mm[:ss]」 */
function formatLocal(date: Date, withSeconds: boolean): string {
  const minutePrecision = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  return withSeconds
    ? `${minutePrecision}:${pad(date.getSeconds())}`
    : minutePrecision
}

/** 后端时间串 → 本地「YYYY-MM-DD HH:mm」；空值 / 不可解析 → 「—」 */
export function formatDateTime(value: string | null | undefined): string {
  const date = parseApiDateTime(value)
  return date ? formatLocal(date, false) : '—'
}

/** 同上，带秒（复核历史等需要秒级精度的行） */
export function formatDateTimeSeconds(
  value: string | null | undefined
): string {
  const date = parseApiDateTime(value)
  return date ? formatLocal(date, true) : '—'
}

/** 毫秒时长 → 「x 秒 / x 分钟 / x 小时 y 分钟 / x 天 y 小时」 */
export function formatElapsed(ms: number | null): string {
  if (ms == null) return '—'
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  if (totalSeconds < 60) return `${totalSeconds} 秒`
  const totalMinutes = Math.floor(totalSeconds / 60)
  if (totalMinutes < 60) return `${totalMinutes} 分钟`
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours < 24) return minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`
  const days = Math.floor(hours / 24)
  const restHours = hours % 24
  return restHours ? `${days} 天 ${restHours} 小时` : `${days} 天`
}

type UsedTimeSource = Pick<
  TaskDetailData,
  'started_at' | 'completed_at' | 'execution_status'
>

/**
 * 任务已用时长：一律以起止时间推算为准（后端 `used_time` 存在「16小时」类异常值，
 * 实测任务只跑约 1 分钟）。进行中任务按「当前 - 开始」实时推算；
 * 无有效开始时间 / 结束时点 → 「—」。
 */
export function formatTaskUsedTime(
  detail: UsedTimeSource,
  now: Date = new Date()
): string {
  const start = parseApiDateTime(detail.started_at)
  if (!start) return '—'
  const completed = parseApiDateTime(detail.completed_at)
  const running =
    detail.execution_status === 'running' || detail.execution_status === 'queued'
  const end = completed ?? (running ? now : null)
  if (!end) return '—'
  return formatElapsed(end.getTime() - start.getTime())
}
