/**
 * SSE 事件 → 通知中心领域模型适配（infrastructure/adapters 层；INT-731 接线）。
 * 事件形状对照 api_gateway/routes/sse_bp.py `_map_event` 与各 emit 实测：
 * - task_progress：data = { task_id, status, total_progress, execution_status, … }（TaskProgressPayload）
 * - report_generated：data = { taskId, reportId, success, status } 或 { taskId, success, error }
 * - import_progress：data = { step, current_table, processed_rows, total_rows, percentage, message }
 * - task_log：data = { log_payload: { level, module, content, time }, task_id, test_case_id }
 * realtime_frame / realtime_summary 高频帧不进通知中心（02_导航栏.md §3.6）。
 */

import type { AppNotification, NotificationKind } from '@/domain/models/notification'
import type { SseEvent } from '@/infrastructure/realtime/sse'

interface TaskProgressEventData {
  task_id?: string | number
  status?: string
  /** 后端 TaskProgressPayload.total_progress（shared/schemas/socket_payloads.py） */
  total_progress?: number
  updated_at?: string
}

interface ReportGeneratedEventData {
  taskId?: string | number
  reportId?: string | number
  success?: boolean
  status?: string
  error?: string
}

interface ImportProgressEventData {
  step?: string
  current_table?: string
  processed_rows?: number
  total_rows?: number
  percentage?: number
  message?: string
}

interface TaskLogEventData {
  log_payload?: {
    id?: string | number
    time?: string
    level?: string
    module?: string
    content?: string
  }
  task_id?: string | number
  test_case_id?: string | number
}

const TASK_LOG_LEVELS = new Set(['ERROR', 'WARNING'])

function nowIso(): string {
  return new Date().toISOString()
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

function asNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

/** 生成稳定去重 id（同任务/报告多次事件按业务 key 合并，最新事件覆盖旧行） */
function makeNoticeId(prefix: string, ref: string): string {
  return `${prefix}:${ref}`
}

/**
 * 映射 SSE 事件 → 通知行（通知页签）。非通知事件返回 null。
 * 名称解析由调用方异步批处理（先以 id 占位，解析完成局部更新，§3.6）。
 */
export function mapSseEventToNotification(event: SseEvent): AppNotification | null {
  switch (event.eventType) {
    case 'task_progress': {
      const data = event.data as TaskProgressEventData | undefined
      const taskId = asString(data?.task_id)
      const progress = Math.round(asNumber(data?.total_progress))
      const updatedAt = asString(data?.updated_at) || nowIso()
      if (!taskId) return null
      return {
        id: makeNoticeId('task', taskId),
        dedupeKey: makeNoticeId('task', taskId),
        tab: 'notice',
        kind: 'task',
        title: `任务 #${taskId}`,
        content: `进度 ${progress}%`,
        createdAt: updatedAt,
        read: false,
        taskId,
      }
    }
    case 'report_generated': {
      const data = event.data as ReportGeneratedEventData | undefined
      const reportId = asString(data?.reportId)
      const success = data?.success !== false
      const updatedAt = nowIso()
      if (!reportId && !data?.taskId) return null
      const key = makeNoticeId('report', reportId || asString(data?.taskId))
      return {
        id: key,
        dedupeKey: key,
        tab: 'notice',
        kind: success ? 'report' : 'error',
        title: reportId ? `报告 #${reportId}` : '报告生成',
        content: success ? '报告已生成' : (asString(data?.error) || '报告生成失败'),
        createdAt: updatedAt,
        read: false,
        reportId: reportId || undefined,
      }
    }
    case 'import_progress': {
      const data = event.data as ImportProgressEventData | undefined
      const percentage = Math.round(asNumber(data?.percentage))
      const updatedAt = nowIso()
      const key = makeNoticeId('import', asString(data?.current_table) || 'batch')
      return {
        id: key,
        dedupeKey: key,
        tab: 'notice',
        kind: 'import',
        title: percentage >= 100 ? '数据导入完成' : '数据导入',
        content: asString(data?.message) || `进度 ${percentage}%`,
        createdAt: updatedAt,
        read: false,
      }
    }
    case 'task_log': {
      const data = event.data as TaskLogEventData | undefined
      const payload = data?.log_payload
      const level = (asString(payload?.level) || '').toUpperCase()
      if (!payload || !TASK_LOG_LEVELS.has(level)) return null
      const updatedAt = asString(payload.time) || nowIso()
      // 按日志 id 去重；无 id（负数合成 id 场景）按任务 + 内容去重，避免同一错误刷屏
      const logRef =
        asString(payload.id) || `${asString(data?.task_id)}:${asString(payload.content)}`
      const key = makeNoticeId('log', logRef)
      return {
        id: key,
        dedupeKey: key,
        tab: 'notice',
        kind: 'error',
        title: `[${level}] ${asString(payload.module) || '任务日志'}`,
        content: asString(payload.content),
        createdAt: updatedAt,
        read: false,
        taskId: asString(data?.task_id) || undefined,
      }
    }
    default:
      // realtime_frame / realtime_summary 及其它事件不进通知中心
      return null
  }
}

/** 通知行语义类型 → 色点 class（任务=info、报告=success、导入=chart-3、错误=destructive） */
export function notificationDotClass(kind: NotificationKind | undefined): string {
  switch (kind) {
    case 'report':
      return 'bg-success'
    case 'import':
      return 'bg-chart-3'
    case 'error':
      return 'bg-destructive'
    case 'task':
    default:
      return 'bg-info'
  }
}
