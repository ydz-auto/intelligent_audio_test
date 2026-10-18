/**
 * 日志实时编排（application 层；17_配置运维.md §4.6/§7.11，INT-693 接线）。
 * 主通道 WS/Socket.IO /ws/logs（subscribe_task + set_filter，§12-1 鉴权待后端立项）
 * 当前不可用 → 走 POST /logs/refresh 轮询兜底（log:manage）：last_id 增量拉取
 * 新日志插顶（newLogs，页面合并到表格顶部）、空闲指数退避至 30s（VITE_LOG_POLL_
 * IDLE_MAX_MS 语义）、速率 条/秒 + 延迟 ms 统计、新日志计数 toast。
 * 实时开关（enabled）与轮询连接状态（connection）同源（验收 3）：开关即启停轮询；
 * 增量拉到新日志时 invalidate 统计缓存，徽章跟随实时刷新。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import type { LogItem, LogRealtimeConfig } from '@/domain/models/log'
import { DEFAULT_REALTIME_CONFIG } from '@/domain/models/log'
import { LOG_STATS_QUERY_KEY, refreshLogs } from '@/infrastructure/api/logsApi'

/** 实时连接状态（§4.6 指示器文案映射；WS 接通后随模块升级切换） */
export type LogRealtimeConnection = 'idle' | 'polling' | 'error'

/** 空闲退避上限（VITE_LOG_POLL_IDLE_MAX_MS 语义：无新日志时轮询放缓至上限 30s） */
const LOG_POLL_IDLE_MAX_MS = 30_000

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

export function useLogRealtime(): LogRealtimeState {
  const queryClient = useQueryClient()
  const [enabled, setEnabledState] = useState(false)
  const [connection, setConnection] = useState<LogRealtimeConnection>('idle')
  const [logRate, setLogRate] = useState(0)
  const [logDelay, setLogDelay] = useState(0)
  const [config, setConfigState] = useState<LogRealtimeConfig>(DEFAULT_REALTIME_CONFIG)
  const [newLogs, setNewLogs] = useState<LogItem[]>([])
  /** 增量基准（null = 未建立：首个轮询仅建基准，存量批不插顶） */
  const lastIdRef = useRef<number | null>(null)
  const idleStreakRef = useRef(0)

  const setConfig = useCallback((patch: Partial<LogRealtimeConfig>) => {
    setConfigState((prev) => ({ ...prev, ...patch }))
  }, [])

  /** 筛选变更 → 清空增量缓冲并重置增量基准（页面在 query 变更时调用） */
  const resetNewLogs = useCallback(() => {
    setNewLogs([])
    lastIdRef.current = null
    idleStreakRef.current = 0
  }, [])

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value)
    if (!value) {
      // 关闭实时：指示器回 idle、清空增量缓冲（表格回到服务端分页态）
      setConnection('idle')
      setLogRate(0)
      setLogDelay(0)
      setNewLogs([])
      lastIdRef.current = null
      idleStreakRef.current = 0
    }
  }, [])

  // 轮询兜底：enabled 时立即拉取一次，之后按 config.pollIntervalMs（空闲指数退避）循环；
  // 配置变更（pollIntervalMs/notifyNewLogs）时重启链条，增量基准跨重启保留。
  useEffect(() => {
    if (!enabled) return
    let stopped = false
    let timer: number | null = null
    let currentDelay = config.pollIntervalMs

    const run = async () => {
      const startedAt = Date.now()
      let nextDelay = config.pollIntervalMs
      try {
        const result = await refreshLogs(lastIdRef.current ?? 0)
        if (stopped) return
        setConnection('polling')
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
        setConnection('error')
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
  }, [enabled, config.pollIntervalMs, config.notifyNewLogs])

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
