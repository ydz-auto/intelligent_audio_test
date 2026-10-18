/**
 * 实时监控 hook（features/logs；17_配置运维.md §4.6）。
 * 主通道 = Socket.IO /ws/logs（log:websocket 判定；socketio_server.py 实测 task_log 事件，
 * set_filter{levels,modules,keyword} 过滤命中逐 sid 下发）；WS 不可用/未授权时降级
 * POST /logs/refresh（log:manage）指数退避轮询（对照 Vue logView.ts REALTIME_POLL 逻辑）。
 * 新日志顶部插入 + 计数 toast「新收到 {n} 条日志」；autoScroll 控制列表滚动。
 */
import { io, type Socket } from 'socket.io-client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { toLog } from '@/infrastructure/adapters/logAdapter'
import type { Log, LogQuery } from '@/domain/models/log'
import { refreshLogs } from '@/infrastructure/api/logsApi'
import {
  REALTIME_POLL_BASE_INTERVAL_MS,
  REALTIME_POLL_IDLE_MAX_MS,
  REALTIME_WS_CONNECT_TIMEOUT_MS,
} from '@/features/logs/constants'

/** 连接状态文案（§4.6 指示器口径） */
export type RealtimeStatus = 'connected' | 'polling' | 'error' | 'pending-auth'

const STATUS_TEXT: Record<RealtimeStatus, string> = {
  connected: '已连接',
  polling: '轮询中',
  error: '连接异常',
  'pending-auth': '实时推送鉴权待后端立项',
}

/** 实时推送入参（task_log wire.log 为 snake_case LogItemDto，toLog 归一） */
function toWireLog(wire: { log?: Log } | null | undefined): Log | null {
  const dto = wire?.log as unknown as Parameters<typeof toLog>[0]
  return dto ? toLog(dto) : null
}

/** WS 过滤（socketio_server.set_filter/match 口径：levels/modules/keyword） */
function buildWsFilter(query: LogQuery): { levels?: string[]; modules?: string[]; keyword?: string } {
  const filter: { levels?: string[]; modules?: string[]; keyword?: string } = {}
  if (query.level) filter.levels = query.level.split(',')
  if (query.module && query.module !== 'all') filter.modules = [query.module]
  if (query.keyword) filter.keyword = query.keyword
  return filter
}

export function useLogRealtime({
  enabled,
  canUseWs,
  canPoll,
  query,
  logs,
  onNewLogs,
  pollBaseIntervalMs = REALTIME_POLL_BASE_INTERVAL_MS,
  toastEnabled = true,
}: {
  /** 实时开关（页面态） */
  enabled: boolean
  /** 持有 log:websocket（§4.6：algo_engineer 可开实时开关订阅 WS） */
  canUseWs: boolean
  /** 持有 log:manage（轮询兜底 refresh 端点需要） */
  canPoll: boolean
  /** 当前筛选条件（WS set_filter + 轮询去重/退避） */
  query: LogQuery
  /** 当前列表行（轮询 lastId 取当前行最大 id） */
  logs: Log[]
  /** 新日志回调（页面顶部插入） */
  onNewLogs: (items: Log[]) => void
  /** 轮询基础间隔（§7.11 实时监控配置 Select，默认 5s） */
  pollBaseIntervalMs?: number
  /** 新日志计数 toast 开关（§7.11） */
  toastEnabled?: boolean
}) {
  const [status, setStatus] = useState<RealtimeStatus>('error')
  const [logRate, setLogRate] = useState(0)
  const [logDelay, setLogDelay] = useState(0)
  const [autoScroll, setAutoScroll] = useState(true)

  const enabledRef = useRef(enabled)
  const queryRef = useRef(query)
  const logsRef = useRef(logs)
  const onNewLogsRef = useRef(onNewLogs)
  const toastEnabledRef = useRef(toastEnabled)
  const pollBaseRef = useRef(pollBaseIntervalMs)
  const generationRef = useRef(0)
  const socketRef = useRef<Socket | null>(null)
  const timerRef = useRef<number | null>(null)

  enabledRef.current = enabled
  queryRef.current = query
  logsRef.current = logs
  onNewLogsRef.current = onNewLogs
  toastEnabledRef.current = toastEnabled
  pollBaseRef.current = pollBaseIntervalMs

  /** 停表停连接（generation 失效防僵尸循环，对照 Vue realtimeLoopGen） */
  const stopAll = useCallback(() => {
    generationRef.current += 1
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (socketRef.current) {
      socketRef.current.removeAllListeners()
      socketRef.current.disconnect()
      socketRef.current = null
    }
  }, [])

  /** 指数退避轮询（POST /logs/refresh 增量，对照 Vue logView.ts:437-514） */
  const startPolling = useCallback((generation: number) => {
    let idleRounds = 0
    const tick = async () => {
      if (generation !== generationRef.current || !enabledRef.current) return
      const pollStart = performance.now()
      const lastId = logsRef.current.reduce((max, log) => Math.max(max, log.id), 0)
      try {
        const result = await refreshLogs(lastId)
        if (generation !== generationRef.current || !enabledRef.current) return
        const elapsed = Math.round(performance.now() - pollStart)
        const newCount = result.newCount ?? result.items.length
        if (newCount > 0) {
          idleRounds = 0
          setLogRate(Math.round((newCount * 1000 * 10) / Math.max(elapsed, 1)) / 10)
          onNewLogsRef.current(result.items)
          if (toastEnabledRef.current) toast.info(`新收到 ${newCount} 条日志`)
        } else {
          idleRounds += 1
          setLogRate(0)
        }
        setLogDelay(elapsed)
        setStatus('polling')
        const delay = Math.min(
          pollBaseRef.current * 2 ** Math.min(idleRounds, 8),
          REALTIME_POLL_IDLE_MAX_MS
        )
        if (generation === generationRef.current && enabledRef.current) {
          timerRef.current = window.setTimeout(tick, delay)
        }
      } catch {
        if (generation === generationRef.current && enabledRef.current) {
          setStatus('error')
          setLogRate(0)
          idleRounds += 1
          const delay = Math.min(
            pollBaseRef.current * 2 ** Math.min(idleRounds, 8),
            REALTIME_POLL_IDLE_MAX_MS
          )
          timerRef.current = window.setTimeout(tick, delay)
        }
      }
    }
    void tick()
  }, [])

  /** WS 订阅（/ws/logs namespace；connect 后 set_filter，task_log 增量插顶） */
  const startWs = useCallback(
    (generation: number) => {
      const socket = io('/ws/logs', {
        transports: ['polling', 'websocket'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 20_000,
        autoConnect: true,
      })
      socketRef.current = socket
      let wsConnected = false
      const timeoutId = window.setTimeout(() => {
        if (!wsConnected && generation === generationRef.current && enabledRef.current) {
          // WS 超时未连上 → 断开降级轮询（canPoll 缺失则保持 error 状态）
          socket.removeAllListeners()
          socket.disconnect()
          socketRef.current = null
          if (canPoll) startPolling(generation)
          else setStatus('error')
        }
      }, REALTIME_WS_CONNECT_TIMEOUT_MS)

      socket.on('connect', () => {
        wsConnected = true
        window.clearTimeout(timeoutId)
        if (generation !== generationRef.current || !enabledRef.current) return
        setStatus('connected')
        setLogDelay(0)
        socket.emit('set_filter', buildWsFilter(queryRef.current))
      })

      socket.on('task_log', (wire: unknown) => {
        if (generation !== generationRef.current || !enabledRef.current) return
        const log = toWireLog(wire as { log?: Log })
        if (!log) return
        onNewLogsRef.current([log])
        if (toastEnabledRef.current) toast.info('新收到 1 条日志')
      })

      socket.on('disconnect', () => {
        if (generation !== generationRef.current || !enabledRef.current) return
        // 已连接后断线 → 停止 WS，降级轮询保活
        socket.removeAllListeners()
        socketRef.current = null
        if (canPoll) {
          setStatus('polling')
          startPolling(generation)
        } else {
          setStatus('error')
        }
      })

      socket.on('connect_error', () => {
        if (generation !== generationRef.current || !enabledRef.current) return
        setLogDelay(Math.round(performance.now() - 0))
      })
    },
    [canPoll, startPolling]
  )

  /** 开启/关闭实时 */
  useEffect(() => {
    if (!enabled) {
      stopAll()
      setLogRate(0)
      setLogDelay(0)
      setStatus('error')
      return
    }
    const generation = ++generationRef.current
    if (canUseWs) {
      startWs(generation)
    } else if (canPoll) {
      setStatus('polling')
      startPolling(generation)
    } else {
      setStatus('pending-auth')
    }
    return () => {
      // 依赖变化（enabled/canUseWs/canPoll）时先停再起
      stopAll()
    }
  }, [enabled, canUseWs, canPoll, startWs, startPolling, stopAll])

  /** 筛选变化 → 轮询退避复位 + WS set_filter 重发 */
  useEffect(() => {
    if (!enabled) return
    if (socketRef.current?.connected) {
      socketRef.current.emit('set_filter', buildWsFilter(query))
    }
  }, [enabled, query])

  const toggleAutoScroll = useCallback(() => setAutoScroll((v) => !v), [])

  return {
    status,
    statusText: STATUS_TEXT[status],
    logRate,
    logDelay,
    autoScroll,
    toggleAutoScroll,
  }
}
