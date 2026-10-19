/**
 * 通知中心领域模型（UX设计-VUE 总表 §2.4 ③）
 *
 * - 通知页签：SSE 事件流（GET /api/v1/sse/events，sse:read），事件含
 *   task_log / task_progress / import_progress / report_generated 等
 * - 公告页签：站点公告（option KV `site.notice`，option:read）
 *
 * 值 = 后端原值，禁止改动值；snake_case ⇄ camelCase 转换在 infrastructure 层。
 */

/** SSE 事件类型（值 = 后端 sse_bp._map_event 下发 event 名原值） */
export const SseEventType = {
  TASK_LOG: 'task_log',
  TASK_PROGRESS: 'task_progress',
  IMPORT_PROGRESS: 'import_progress',
  REPORT_GENERATED: 'report_generated',
  SECONDARY_COMPARE_GENERATED: 'secondary_compare_generated',
  REALTIME_FRAME: 'realtime_frame',
  REALTIME_SUMMARY: 'realtime_summary',
} as const

export type SseEventTypeValue = typeof SseEventType[keyof typeof SseEventType]

/** 通知中心单条事件（前端聚合模型） */
export interface SseNotificationEvent {
  /** SSE 事件名（event: xxx） */
  event: string
  /** SSE 事件载荷（data JSON 已解析） */
  data: Record<string, unknown>
  /** 前端接收时间（ISO，用于展示与去重） */
  receivedAt: string
}

/** 站点公告（option KV site.notice；公告页签数据源） */
export interface SiteNotice {
  content: string
  updatedAt: string
}
