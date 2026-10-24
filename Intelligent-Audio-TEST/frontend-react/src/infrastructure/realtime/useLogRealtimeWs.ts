/**
 * 日志实时 WS/Socket.IO /ws/logs 主通道（infrastructure/realtime 层；17_配置运维.md §4.6，INT-928 接线）。
 * socket.io-client 连 /ws/logs 命名空间：connect 后 emit set_filter（levels/modules/keyword/task_id，
 * socketio_server.py:48-94 match 契约）+ subscribe_task/unsubscribe_task（task_id 房间订阅）；
 * 监听 task_log 事件（wire {task_id, log}，socketio_server.py:122-125）与 logs/LOG_BATCH 批量事件
 * → 经 log.dto toLogFromWs 转 Domain LogItem 回调。
 * 断线由 socket.io 自动重连（指数退避）；状态机 connecting → connected / error，由 application 层
 * useLogRealtime 据此在「WS 主通道 ↔ POST /logs/refresh 轮询兜底」间切换（本层只管 WS 主通道）。
 * 鉴权待后端立项（§12-1）：/socket.io 白名单免认证 + connect 无 token 校验，通道现即可连；
 * auth 注入 token 仅为前向兼容，后端当前忽略。
 *
 * transport 固定 websocket（INT-1685）：engine.io 会话（sid、房间订阅、上行队列）只存在于接住握手的
 * 那一个 uvicorn worker 里，而同一容器的多 worker 共享一个监听 socket；polling 的后续 HTTP 请求会被
 * 内核分给任意 worker，落到别的进程即「会话未知」（4 worker 实测 websocket-only 6/6，带 polling 3/6）。
 * websocket 是单条长连接，不依赖会话粘滞，多 worker 与粘滞无关；不配 polling 回退，连不上交由
 * application 层切 POST /logs/refresh 轮询兜底。
 */
import { io, type Socket } from 'socket.io-client'
import { useEffect, useRef, useState } from 'react'

import type { LogItem } from '@/domain/models/log'
import { toLogFromWs, type LogWsTaskLogDto } from '@/infrastructure/dto/log.dto'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

/** WS 主通道连接状态（application 层据此切 WS/轮询兜底） */
export type LogRealtimeWsStatus = 'idle' | 'connecting' | 'connected' | 'error'

/** set_filter 订阅条件（仅后端 match 支持的四个维度；页面 query 超集在此收敛） */
export interface LogWsFilter {
  levels?: string[]
  modules?: string[]
  keyword?: string
  taskId?: number | string
}

export interface UseLogRealtimeWsOptions {
  enabled: boolean
  filter: LogWsFilter
  /** 每条 task_log/LOG_BATCH 日志经 toLogFromWs 转 Domain 后回调 */
  onLog: (log: LogItem) => void
}

/** set_filter + 任务房间订阅下发（filter 变更多次调用幂等，后端按 sid 覆盖） */
function applyLogWsFilter(socket: Socket, filter: LogWsFilter): void {
  socket.emit('set_filter', {
    levels: filter.levels?.length ? filter.levels : undefined,
    modules: filter.modules?.length ? filter.modules : undefined,
    keyword: filter.keyword || undefined,
    task_id:
      filter.taskId !== undefined && filter.taskId !== '' ? String(filter.taskId) : undefined,
  })
  if (filter.taskId !== undefined && filter.taskId !== '') {
    socket.emit('subscribe_task', { task_id: String(filter.taskId) })
  } else {
    socket.emit('unsubscribe_task', {})
  }
}

/** LOG_BATCH 批量事件解析：兼容 {type, data:[...]} 与裸数组两形（legacy connection_manager） */
function extractLogBatch(data: unknown): LogWsTaskLogDto[] {
  if (Array.isArray(data)) return data as LogWsTaskLogDto[]
  if (typeof data === 'object' && data !== null) {
    const batch = (data as { data?: unknown }).data
    if (Array.isArray(batch)) return batch as LogWsTaskLogDto[]
  }
  return []
}

/**
 * 订阅 /ws/logs 主通道。enabled 开启连接、关闭断开；filter 变更重发 set_filter。
 * 返回连接状态（state），onLog 经 ref 转发避免闭包陈旧。
 */
export function useLogRealtimeWs(options: UseLogRealtimeWsOptions): LogRealtimeWsStatus {
  const { enabled, filter, onLog } = options
  const [status, setStatus] = useState<LogRealtimeWsStatus>('idle')
  const socketRef = useRef<Socket | null>(null)
  const filterRef = useRef(filter)
  filterRef.current = filter
  const onLogRef = useRef(onLog)
  onLogRef.current = onLog

  // 连接生命周期：enabled 时建立，关闭/卸载时断开
  useEffect(() => {
    if (!enabled) {
      socketRef.current?.disconnect()
      socketRef.current = null
      setStatus('idle')
      return
    }

    const token = authTokenStore.get()
    const socket = io('/ws/logs', {
      path: '/socket.io',
      transports: ['websocket'],
      timeout: 5_000, // 握手超时 5s 内判 WS 不可用 → application 层降级轮询兜底
      reconnection: true,
      reconnectionDelay: 1_000,
      reconnectionDelayMax: 8_000,
      reconnectionAttempts: Number.POSITIVE_INFINITY,
      auth: token ? { token } : undefined,
    })
    socketRef.current = socket
    setStatus('connecting')

    const handleTaskLog = (data: unknown) => {
      const log = toLogFromWs(data as LogWsTaskLogDto | null)
      if (log) onLogRef.current(log)
    }

    const handleLogsBatch = (data: unknown) => {
      for (const dto of extractLogBatch(data)) {
        const log = toLogFromWs(dto)
        if (log) onLogRef.current(log)
      }
    }

    socket.on('connect', () => {
      setStatus('connected')
      applyLogWsFilter(socket, filterRef.current)
    })
    socket.on('connect_error', () => {
      // 连接失败/握手超时 → WS 不可用，交由 application 层切轮询兜底；socket.io 后台继续重连
      setStatus('error')
    })
    socket.on('disconnect', (reason) => {
      // 主动断开（io client disconnect）由清理路径处理；被动断开 → 重连期间按不可用上报
      if (reason === 'io client disconnect') return
      setStatus('error')
    })
    socket.on('task_log', handleTaskLog)
    socket.on('logs', handleLogsBatch)

    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [enabled])

  // 筛选变更 → 重发 set_filter/subscribe_task（连接存活时）
  useEffect(() => {
    const socket = socketRef.current
    if (enabled && socket?.connected) {
      applyLogWsFilter(socket, filter)
    }
  }, [enabled, filter])

  return status
}
