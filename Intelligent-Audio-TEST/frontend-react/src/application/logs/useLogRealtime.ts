/**
 * 日志实时编排（application 层；17_配置运维.md §4.6/§7.11，INT-928 接线）。
 * 主通道 WS/Socket.IO /ws/logs（消费 realtime/useLogRealtimeWs：subscribe_task + set_filter，
 * task_log/LOG_BATCH 事件增量插顶）——WS 已连即纯 WS 主通道，无轮询请求；
 * WS 不可用（connect_error/被动断线）降级 POST /logs/refresh 轮询兜底（log:manage）：
 * last_id 增量拉取、新日志插顶（newLogs，页面合并到表格顶部）、空闲指数退避至 30s
 * （VITE_LOG_POLL_IDLE_MAX_MS 语义）、速率 条/秒 + 延迟 ms 统计、新日志计数 toast。
 * 实时开关（enabled）按 log:websocket 判定（页面传入）；refresh 兜底可用性按 log:manage
 * （algo_engineer 持 log:websocket 无 log:manage → 仅 WS 主通道，WS 不可用即实时不可用）。
 * 增量拉到新日志时 invalidate 统计缓存，徽章跟随实时刷新。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import type { LogItem, LogRealtimeConfig } from '@/domain/models/log'
import { LOG_STATS_QUERY_KEY, refreshLogs } from '@/infrastructure/api/logsApi'
import {
  useLogRealtimeWs,
  type LogWsFilter,
} from '@/infrastructure/realtime/useLogRealtimeWs'

/** 实时连接状态（§4.6 指示器文案映射；ws=主通道已连 / polling=轮询兜底） */
export type LogRealtimeConnection = 'idle' | 'connecting' | 'ws' | 'polling' | 'error'

/** 空闲退避上限（VITE_LOG_POLL_IDLE_MAX_MS 语义：无新日志时轮询放缓至上限 30s） */
const LOG_POLL_IDLE_MAX_MS = 30_000

/** 缺省实时配置（页面经 features/logs/constants DEFAULT_REALTIME_CONFIG 传入；此处兜底同值） */
const FALLBACK_REALTIME_CONFIG: LogRealtimeConfig = {
  pollIntervalMs: 5_000,
  autoScroll: true,
  notifyNewLogs: true,
}

/** WS 订阅 + 轮询兜底来源（页面传入：WS set_filter 条件 + 是否持 log:manage） */
export interface LogRealtimeSource {
  /** WS set_filter 订阅条件（levels/modules/keyword/task_id，§4.6 match 契约） */
  wsFilter: LogWsFilter
  /** POST /logs/refresh 轮询兜底可用（log:manage；algo_engineer 无此码 → 仅 WS 主通道） */
  canPollFallback: boolean
}

export type LogRealtimeState = {
  enabled: boolean
  setEnabled: (value: boolean) => void
  connection: LogRealtimeConnection
  logRate: number
  logDelay: number
  config: LogRealtimeConfig
  setConfig: (patch: Partial<LogRealtimeConfig>) => void
  newLogs: LogItem[]
  resetNewLogs: () => void
}

export function useLogRealtime(
  initialConfig?: LogRealtimeConfig,
  source?: LogRealtimeSource
): LogRealtimeState {
  const queryClient = useQueryClient()
  const [enabled, setEnabledState] = useState(false)
  const [logRate, setLogRate] = useState(0)
  const [logDelay, setLogDelay] = useState(0)
  const [config, setConfigState] = useState<LogRealtimeConfig>(
    initialConfig ?? FALLBACK_REALTIME_CONFIG
  )
  const [newLogs, setNewLogs] = useState<LogItem[]>([])
  /** 增量基准（null = 未建立：首个轮询仅建基准，存量批不插顶） */
  const lastIdRef = useRef<number | null>(null)
  const idleStreakRef = useRef(0)
  /** WS 事件到达时间窗（滚动 1s，速率/延迟统计） */
  const wsEventsRef = useRef<number[]>([])
  /** WS 计数 toast 防抖聚合（避免每条日志一弹） */
  const wsToastTimerRef = useRef<number | null>(null)
  const wsToastCountRef = useRef(0)
  const configRef = useRef(config)
  configRef.current = config
  const canPollRef = useRef(Boolean(source?.canPollFallback))
  canPollRef.current = Boolean(source?.canPollFallback)

  const setConfig = useCallback((patch: Partial<LogRealtimeConfig>) => {
    setConfigState((prev) => ({ ...prev, ...patch }))
  }, [])

  /** WS task_log 到达 → 插顶 + 速率/延迟 + 计数 toast（聚合防抖 800ms） */
  const handleWsLog = useCallback((log: LogItem) => {
    const now = Date.now()
    setNewLogs((prev) => {
      const seen = new Set(prev.map((item) => item.id))
      return seen.has(log.id) ? prev : [log, ...prev]
    })
    lastIdRef.current = Math.max(lastIdRef.current ?? 0, log.id)
    // 速率：1s 滚动窗内事件数；延迟：相邻事件到达间隔
    const recent = wsEventsRef.current.filter((t) => now - t < 1_000)
    wsEventsRef.current = [...recent, now]
    setLogRate(wsEventsRef.current.length)
    const prev = recent[recent.length - 1]
    setLogDelay(prev !== undefined ? now - prev : 0)
    // 计数 toast 聚合：800ms 窗口合并，避免高频日志逐条弹 toast
    if (configRef.current.notifyNewLogs) {
      wsToastCountRef.current += 1
      if (wsToastTimerRef.current === null) {
        wsToastTimerRef.current = window.setTimeout(() => {
          wsToastTimerRef.current = null
          const count = wsToastCountRef.current
          wsToastCountRef.current = 0
          if (count > 0) toast.info(`新收到 ${count} 条日志`)
        }, 800)
      }
    }
  }, [])

  const wsStatus = useLogRealtimeWs({
    enabled,
    filter: source?.wsFilter ?? {},
    onLog: handleWsLog,
  })

  /** 筛选变更 → 清空增量缓冲并重置增量基准（页面在 query 变更时调用） */
  const resetNewLogs = useCallback(() => {
    setNewLogs([])
    lastIdRef.current = null
    idleStreakRef.current = 0
    wsEventsRef.current = []
    if (wsToastTimerRef.current !== null) {
      window.clearTimeout(wsToastTimerRef.current)
      wsToastTimerRef.current = null
    }
    wsToastCountRef.current = 0
  }, [])

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value)
    if (!value) {
      // 关闭实时：清空增量缓冲（表格回到服务端分页态）与统计
      setLogRate(0)
      setLogDelay(0)
      setNewLogs([])
      lastIdRef.current = null
      idleStreakRef.current = 0
      wsEventsRef.current = []
      if (wsToastTimerRef.current !== null) {
        window.clearTimeout(wsToastTimerRef.current)
        wsToastTimerRef.current = null
      }
      wsToastCountRef.current = 0
    }
  }, [])

  /** 连接状态派生：WS 已连=主通道；连接中=connecting；error=兜底轮询或实时不可用 */
  const connection = useMemo<LogRealtimeConnection>(() => {
    if (!enabled) return 'idle'
    if (wsStatus === 'connected') return 'ws'
    if (wsStatus === 'connecting' || wsStatus === 'idle') return 'connecting'
    // wsStatus 'error'：WS 不可用 → 有 log:manage 降级轮询兜底，否则实时不可用
    return canPollRef.current ? 'polling' : 'error'
  }, [enabled, wsStatus])

  // 轮询兜底：enabled 且 WS 已不可用（error）且持 log:manage 时循环；
  // WS 恢复已连（socket.io 后台重连）即停止本链，主通道交还 WS。
  useEffect(() => {
    if (!enabled) return
    if (wsStatus === 'connected' || wsStatus === 'connecting' || wsStatus === 'idle') return
    if (!canPollRef.current) return
    let stopped = false
    let timer: number | null = null
    let currentDelay = config.pollIntervalMs

    const run = async () => {
      const startedAt = Date.now()
      let nextDelay = config.pollIntervalMs
      try {
        const result = await refreshLogs(lastIdRef.current ?? 0)
        if (stopped) return
        setLogDelay(Date.now() - startedAt)

        if (result.resetRequired) {
          // 服务端滚动/清库：重置基准，避免错乱
          lastIdRef.current = null
          setNewLogs([])
          idleStreakRef.current = 0
        } else if (lastIdRef.current === null) {
          // 首次/重置后的首个轮询：仅建立增量基准，存量批不插顶
          lastIdRef.current = result.lastId
          setNewLogs([])
          idleStreakRef.current = 0
          setLogRate(0)
        } else if (result.items.length > 0) {
          // 增量批 → 插顶 + 计数 toast + 速率（条/秒）
          setNewLogs((prev) => {
            const seen = new Set(prev.map((log) => log.id))
            const fresh = result.items.filter((log) => !seen.has(log.id))
            return [...fresh, ...prev] // 新日志插顶（§4.6）
          })
          lastIdRef.current = Math.max(lastIdRef.current, result.lastId)
          idleStreakRef.current = 0
          setLogRate(result.items.length / (currentDelay / 1000))
          if (config.notifyNewLogs) {
            toast.info(`新收到 ${result.items.length} 条日志`)
          }
        } else {
          idleStreakRef.current += 1
          setLogRate(0)
        }
      } catch {
        if (stopped) return
        setLogDelay(Date.now() - startedAt)
        idleStreakRef.current += 1
      }
      // 空闲指数退避：无新日志每档 ×2，封顶 30s
      if (idleStreakRef.current > 0) {
        nextDelay = Math.min(
          config.pollIntervalMs * 2 ** idleStreakRef.current,
          LOG_POLL_IDLE_MAX_MS
        )
      }
      if (!stopped) {
        currentDelay = nextDelay
        timer = window.setTimeout(() => {
          void run()
        }, currentDelay)
      }
    }

    void run()
    return () => {
      stopped = true
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [enabled, wsStatus, config.pollIntervalMs, config.notifyNewLogs])

  // 实时增量拉到新日志 → 统计徽章跟随刷新（短 TTL 同源，验收 3）
  useEffect(() => {
    if (newLogs.length > 0) {
      void queryClient.invalidateQueries({ queryKey: LOG_STATS_QUERY_KEY })
    }
  }, [newLogs, queryClient])

  return {
    enabled,
    setEnabled,
    connection,
    logRate,
    logDelay,
    config,
    setConfig,
    newLogs,
    resetNewLogs,
  }
}
