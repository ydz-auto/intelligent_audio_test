/**
 * 通知中心 infrastructure API（infrastructure/api 层；INT-731 接线）。
 * 数据源对照 02_导航栏.md §3.6：
 * - 通知页签 = SSE 事件流（GET /api/v1/sse/events，sse:read）——复用基座
 *   infrastructure/realtime/sse.ts 的 subscribeSse（断线指数退避重连已有）。
 * - 公告页签 = 站点公告（system_options.site.notice，option API 读取，
 *   复用 optionApi.getSystemOptions；未配置为空态）。
 * - 任务名/报告名：task_progress → GET /tasks/{id}，report_generated →
 *   GET /reports/{id}（name 回退 task_name）；解析失败降级「任务 #id / 报告 #id」。
 */
import { mapSseEventToNotification } from '@/infrastructure/adapters/notificationAdapter'
import {
  subscribeSse,
  SSE_EVENT_CHANNELS,
  type SseEvent,
  type SseStatus,
} from '@/infrastructure/realtime/sse'
import { fetchReportDetail } from '@/infrastructure/api/reports-api'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import type { AppNotification } from '@/domain/models/notification'

/** 通知中心订阅通道（TASK + REPORT；CASE/DEVICE/CONFIG 后端暂未映射推送） */
const NOTIFICATION_CHANNELS = [
  SSE_EVENT_CHANNELS.TASK_EVENTS,
  SSE_EVENT_CHANNELS.REPORT_EVENTS,
]

export interface NotificationStreamHandlers {
  onEvent: (item: AppNotification) => void
  onStatusChange?: (status: SseStatus) => void
  signal?: AbortSignal
}

/**
 * 订阅通知事件流：订阅 SSE 五通道中的 TASK/REPORT，经适配器映射为通知行。
 * 返回解绑函数（组件卸载/登出时调用）。
 */
export function subscribeNotificationStream(
  handlers: NotificationStreamHandlers
): () => void {
  return subscribeSse({
    channels: NOTIFICATION_CHANNELS,
    signal: handlers.signal,
    onStatusChange: handlers.onStatusChange,
    onEvent: (event: SseEvent) => {
      const item = mapSseEventToNotification(event)
      if (item) handlers.onEvent(item)
    },
  })
}

/** 名称解析缓存（按 id 去重；解析失败也缓存降级文案避免反复请求） */
const taskNameCache = new Map<string, string>()
const reportNameCache = new Map<string, string>()

function fallbackTaskName(taskId: string): string {
  return `任务 #${taskId}`
}

function fallbackReportName(reportId: string): string {
  return `报告 #${reportId}`
}

/** 任务名解析：GET /tasks/{id} → name；失败降级「任务 #id」 */
export async function resolveTaskName(taskId: string): Promise<string> {
  const cached = taskNameCache.get(taskId)
  if (cached) return cached
  try {
    const detail = await fetchTaskDetail(Number(taskId))
    const name = detail?.name?.trim()
    const resolved = name || fallbackTaskName(taskId)
    taskNameCache.set(taskId, resolved)
    return resolved
  } catch {
    const fallback = fallbackTaskName(taskId)
    taskNameCache.set(taskId, fallback)
    return fallback
  }
}

/** 报告名解析：GET /reports/{id} → name（回退 task_name）；失败降级「报告 #id」 */
export async function resolveReportName(reportId: string): Promise<string> {
  const cached = reportNameCache.get(reportId)
  if (cached) return cached
  try {
    const detail = await fetchReportDetail(Number(reportId))
    const name = detail?.name?.trim() || detail?.task_name?.trim()
    const resolved = name || fallbackReportName(reportId)
    reportNameCache.set(reportId, resolved)
    return resolved
  } catch {
    const fallback = fallbackReportName(reportId)
    reportNameCache.set(reportId, fallback)
    return fallback
  }
}

/**
 * 为通知行解析真实名称并返回更新后的通知（名称解析失败保留原降级标题）。
 * 异步批处理由调用方编排（不阻塞事件行渲染，§3.6）。
 */
export async function resolveNotificationNames(
  item: AppNotification
): Promise<AppNotification> {
  if (item.taskId && item.kind === 'task') {
    const name = await resolveTaskName(item.taskId)
    if (name && !name.startsWith('任务 #')) {
      return { ...item, title: name }
    }
  }
  if (item.reportId && item.kind === 'report') {
    const name = await resolveReportName(item.reportId)
    if (name && !name.startsWith('报告 #')) {
      return { ...item, title: name }
    }
  }
  return item
}
