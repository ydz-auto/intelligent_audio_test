/**
 * 通知中心 API（UX设计-VUE 总表 §2.4 ③）
 *
 * 数据源：
 * - 通知页签：GET /api/v1/sse/events（sse:read，SSE 事件流，五通道
 *   task_log/task_progress/import_progress/report_generated 等，api_gateway/routes/sse_bp.py）
 * - 公告页签：option KV `site.notice`（optionsApi.getSiteNotice）
 *
 * SSE 为长连流（text/event-stream + 心跳注释），浏览器用原生 EventSource；
 * 本模块只暴露「连接 + 逐事件回调」，由组件层管理生命周期（打开时连接/关闭断开）。
 */
import type { SseNotificationEvent } from '../../domain/model/notification'

const SSE_EVENTS_URL = '/api/v1/sse/events'

export interface SseConnection {
  close: () => void
  readyState: () => number
}

/**
 * 建立 SSE 事件流连接。onEvent 逐条回调（含事件名 + 解析后载荷 + 接收时间）。
 * 仅当后端认证开启且已登录（sse:read）时后端才推送；未登录连接后端 401。
 * 返回 SseConnection（close 断开）。
 */
export function connectSseEvents(onEvent: (event: SseNotificationEvent) => void): SseConnection {
  let source: EventSource | null = null
  let closed = false

  try {
    source = new EventSource(SSE_EVENTS_URL)
  } catch {
    // EventSource 不可用（如 Electron file:// 协议）：静默降级为空连接
    return {
      close: () => { closed = true },
      readyState: () => EventSource?.CLOSED ?? 2,
    }
  }

  const dispatch = (eventName: string, rawData: string | null) => {
    if (closed) return
    let data: Record<string, unknown> = {}
    if (rawData) {
      try {
        data = JSON.parse(rawData) as Record<string, unknown>
      } catch {
        data = { raw: rawData }
      }
    }
    onEvent({
      event: eventName,
      data,
      receivedAt: new Date().toISOString(),
    })
  }

  // 具名事件（后端 sse_bp._map_event 下发的 event: xxx）
  const EVENT_NAMES = [
    'task_log', 'task_progress', 'import_progress',
    'report_generated', 'secondary_compare_generated',
    'realtime_frame', 'realtime_summary',
  ]
  for (const name of EVENT_NAMES) {
    source.addEventListener(name, (e: MessageEvent) => dispatch(name, e.data as string))
  }
  // 默认事件（event: message）兜底
  source.onmessage = (e: MessageEvent) => dispatch('message', e.data as string)

  source.onerror = () => {
    // EventSource 自动重连（浏览器内建）；组件层可监听 readyState 判断状态
  }

  return {
    close: () => {
      closed = true
      source?.close()
    },
    readyState: () => source?.readyState ?? EventSource.CLOSED,
  }
}
