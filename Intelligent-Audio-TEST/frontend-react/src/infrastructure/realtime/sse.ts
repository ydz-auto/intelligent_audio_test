/**
 * SSE 事件流订阅（infrastructure/realtime 层；接线基座 INT-605）。
 *
 * 端点：GET /api/v1/sse/events（api_gateway/routes/sse_bp.py），服务端订阅
 * EventBus 五通道（EventChannel 枚举）实时推送任务/用例/设备/报告/配置事件。
 * 必须用 fetch + ReadableStream 解析（EventSource 无法携带 Authorization
 * 头——/sse/events 需 sse:read 权限），token 由本模块直接注入。
 *
 * 能力：五通道枚举 + 事件名→通道映射（sse_bp._map_event 口径） + 断线指数
 * 退避重连 + 心跳超时判活 + 同事件去重（防重连重复推送）。
 */

import { API_BASE_URL } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

/** 五通道（值 = shared.utils.redis_pubsub.EventChannel 原值，禁止改动） */
export const SSE_EVENT_CHANNELS = {
  TASK_EVENTS: 'task_events',
  CASE_EVENTS: 'case_events',
  DEVICE_EVENTS: 'device_events',
  REPORT_EVENTS: 'report_events',
  CONFIG_EVENTS: 'config_events',
} as const

export type SseChannel =
  (typeof SSE_EVENT_CHANNELS)[keyof typeof SSE_EVENT_CHANNELS]

/** 事件名 → 通道映射（sse_bp._map_event 口径；CASE/DEVICE/CONFIG 后端暂未映射推送） */
const EVENT_TO_CHANNEL: Record<string, SseChannel> = {
  task_log: SSE_EVENT_CHANNELS.TASK_EVENTS,
  task_progress: SSE_EVENT_CHANNELS.TASK_EVENTS,
  import_progress: SSE_EVENT_CHANNELS.TASK_EVENTS,
  report_generated: SSE_EVENT_CHANNELS.REPORT_EVENTS,
  secondary_compare_generated: SSE_EVENT_CHANNELS.REPORT_EVENTS,
  realtime_frame: SSE_EVENT_CHANNELS.REPORT_EVENTS,
  realtime_summary: SSE_EVENT_CHANNELS.REPORT_EVENTS,
}

export interface SseEvent {
  /** 事件归属通道（未知事件名回退 payload.channel，仍未知为 undefined） */
  channel: SseChannel | undefined
  eventType: string
  data: unknown
  id: string | undefined
}

export type SseStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface SseSubscribeOptions {
  /** 订阅通道子集；缺省订阅全部五通道（未知通道事件仍透传 onEvent） */
  channels?: SseChannel[]
  onEvent: (event: SseEvent) => void
  onStatusChange?: (status: SseStatus) => void
  signal?: AbortSignal
  /** 重连退避初值（ms），默认 2000 */
  reconnectBaseMs?: number
  /** 重连退避上限（ms），默认 30000 */
  reconnectMaxMs?: number
  /** 心跳超时（ms），超过判为断连触发重连，默认 30000 */
  heartbeatTimeoutMs?: number
}

/** 同事件去重窗口（单订阅内重连后重复推送同一事件时跳过；每订阅独立作用域，跨订阅不误杀） */
const DEDUP_WINDOW_MS = 5_000

function routeChannel(eventType: string, data: unknown): SseChannel | undefined {
  const mapped = EVENT_TO_CHANNEL[eventType]
  if (mapped) return mapped
  if (typeof data === 'object' && data !== null) {
    const channel = (data as Record<string, unknown>).channel
    if (typeof channel === 'string' && channel in SSE_EVENT_CHANNELS) {
      return channel as SseChannel
    }
  }
  return undefined
}

interface Frame {
  eventType: string
  data: unknown
  id: string | undefined
  /** 服务端 retry 字段（重连建议延迟；缺省走本地指数退避） */
  retry: number | undefined
}

function parseFrame(raw: string): Frame | null {
  let eventType = 'message'
  let id: string | undefined
  let retry: number | undefined
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue // 注释/心跳
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') eventType = value
    else if (field === 'data') dataLines.push(value)
    else if (field === 'id') id = value
    else if (field === 'retry') retry = Number(value)
  }
  if (dataLines.length === 0 && eventType === 'message') return null
  let data: unknown = dataLines.join('\n')
  if (eventType !== 'message') {
    try {
      data = JSON.parse(data as string)
    } catch {
      // 事件名帧但 data 非 JSON：原样字符串透传
    }
  }
  return { eventType, data, id, retry }
}

/**
 * 订阅 /api/v1/sse/events。返回解绑函数（调用后断开连接并停止重连）。
 * 断线/心跳超时自动重连（指数退避）；同事件去重；signal.abort 终止。
 */
export function subscribeSse(options: SseSubscribeOptions): () => void {
  const {
    channels,
    onEvent,
    onStatusChange,
    signal,
    reconnectBaseMs = 2_000,
    reconnectMaxMs = 30_000,
    heartbeatTimeoutMs = 30_000,
  } = options

  // 去重作用域绑定到本订阅实例（INT-935：全局共享会误杀同事件的多订阅方——
  // 通知中心与报告生成进度并行订阅同一事件时，后到者被误判为重连重复而丢失）
  const lastEvents = new Map<string, { key: string; at: number }>()
  const isDuplicate = (eventType: string, data: unknown): boolean => {
    const key = `${eventType}:${JSON.stringify(data)}`
    const now = Date.now()
    const last = lastEvents.get(eventType)
    if (last && last.key === key && now - last.at < DEDUP_WINDOW_MS) {
      return true
    }
    lastEvents.set(eventType, { key, at: now })
    return false
  }

  let stopped = false
  let attempt = 0
  let serverRetryMs: number | undefined
  let controller: AbortController | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let lastFrameAt = Date.now()
  /** 当前 connect 注册在外部 signal 上的 abort 监听（重连/teardown 时摘除） */
  let signalAbortListener: (() => void) | null = null

  function setStatus(status: SseStatus): void {
    if (!stopped) onStatusChange?.(status)
  }

  function stopHeartbeat(): void {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function startHeartbeat(): void {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (Date.now() - lastFrameAt > heartbeatTimeoutMs) {
        // 心跳超时判死，强制断开触发重连
        controller?.abort()
      }
    }, heartbeatTimeoutMs / 2)
  }

  function scheduleReconnect(): void {
    if (stopped) return
    attempt += 1
    // 服务端 retry 字段优先；缺省按本地指数退避（初值 × 2^(attempt-1)，封顶）
    const backoff = Math.min(
      reconnectBaseMs * 2 ** (attempt - 1),
      reconnectMaxMs
    )
    const delay = serverRetryMs ?? backoff
    setStatus('reconnecting')
    reconnectTimer = setTimeout(() => {
      void connect()
    }, delay)
  }

  function handleFrame(raw: string): void {
    lastFrameAt = Date.now()
    const frame = parseFrame(raw)
    if (!frame) return
    if (frame.eventType === 'message') return
    if (frame.retry !== undefined && Number.isFinite(frame.retry) && frame.retry > 0) {
      serverRetryMs = frame.retry
    }
    if (isDuplicate(frame.eventType, frame.data)) return
    const channel = routeChannel(frame.eventType, frame.data)
    if (channels && channel !== undefined && !channels.includes(channel)) return
    onEvent({
      channel,
      eventType: frame.eventType,
      data: frame.data,
      id: frame.id,
    })
  }

  async function connect(): Promise<void> {
    if (stopped) return
    controller = new AbortController()
    if (signal) {
      // 重连会再次 connect：先摘旧监听，避免同 signal 重复注册累积
      if (signalAbortListener) {
        signal.removeEventListener('abort', signalAbortListener)
        signalAbortListener = null
      }
      if (signal.aborted) {
        stopped = true
        teardown()
        return
      }
      const onAbort = (): void => {
        stopped = true
        teardown()
      }
      signalAbortListener = onAbort
      signal.addEventListener('abort', onAbort, { once: true })
    }

    setStatus(attempt === 0 ? 'connecting' : 'reconnecting')
    const token = authTokenStore.get()
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    }
    if (token) headers.Authorization = `Bearer ${token}`

    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}/sse/events`, {
        headers,
        signal: controller.signal,
      })
    } catch {
      scheduleReconnect()
      return
    }
    if (!response.ok || !response.body) {
      scheduleReconnect()
      return
    }

    setStatus('open')
    attempt = 0
    startHeartbeat()

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let sep = buffer.indexOf('\n\n')
        while (sep !== -1) {
          const raw = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          handleFrame(raw)
          sep = buffer.indexOf('\n\n')
        }
      }
      // 流正常结束（服务端关闭）→ 重连
      scheduleReconnect()
    } catch {
      if (!stopped) scheduleReconnect()
    } finally {
      stopHeartbeat()
    }
  }

  function teardown(): void {
    // 首行置 stopped（置于 abort 之前）：杜绝「连接 OPEN 且 read 挂起时解绑 →
    // controller.abort() 抛 AbortError → catch 分支误排重连」的终止失效路径；
    // scheduleReconnect 的 if (stopped) return 共同兜底。
    stopped = true
    if (signal && signalAbortListener) {
      signal.removeEventListener('abort', signalAbortListener)
      signalAbortListener = null
    }
    stopHeartbeat()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    controller?.abort()
  }

  void connect()

  return teardown
}
