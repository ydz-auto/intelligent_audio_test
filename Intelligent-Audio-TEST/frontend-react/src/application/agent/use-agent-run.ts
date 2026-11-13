/**
 * Agent Run 编排（application 层；doc/agent化/07_单Agent_Skills落地方案.md §9/§11/§12.2）。
 *
 * 职责：发起 run（首次自动建会话）→ 订阅 SSE → 断线续传（Last-Event-ID + cursor）
 * → 取消（同一 run 只发一次取消请求）→ 错误归一。
 * 事件去重：全局 sequence 单调 + message_delta 按 message_id 记录最大 sequence，
 * 重连回放不会重复渲染同一段文本。
 *
 * 本 hook 只维护 run 生命周期与事件转发；不拼装页面消息体（ChatMessage 补丁在
 * features/ai-chat/hooks/use-chat-handler）。所有对外状态均为 camelCase。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  AGENT_ERROR_COPY,
  AGENT_EVENT_TYPE,
  isTerminalRunStatus,
  type AgentRun,
  type AgentRunEvent,
  type AgentRunStatus,
} from '@/domain/models/agent'
import {
  AGENT_STREAM_STATUS,
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  getAgentRun,
  subscribeAgentRunEvents,
  toAgentErrorMessage,
  type AgentStreamStatus,
} from '@/infrastructure/api/agentApi'

/** Run 生命周期阶段（idle 未开始；cancelling 已发取消请求等终态） */
export const AGENT_RUN_PHASE = {
  IDLE: 'idle',
  PREPARING: 'preparing',
  RUNNING: 'running',
  RECONNECTING: 'reconnecting',
  CANCELLING: 'cancelling',
  FINISHED: 'finished',
  ERROR: 'error',
} as const

export type AgentRunPhase =
  (typeof AGENT_RUN_PHASE)[keyof typeof AGENT_RUN_PHASE]

/** 取消后若服务端未推 run_finished，延迟核对 run 快照（ms） */
const CANCEL_RECONCILE_DELAY_MS = 2_000

/** 会话标题取首条消息前若干字符（后端缺省时也可自行生成，便于会话列表识别） */
const SESSION_TITLE_MAX_LENGTH = 32

export interface UseAgentRunHandlers {
  /** 去重后的领域事件（消息增量 / 工具卡 / 终态 / 错误） */
  onEvent?: (event: AgentRunEvent) => void
  onPhaseChange?: (phase: AgentRunPhase) => void
  /** 错误归一后的中文文案（页面落 error 消息态） */
  onError?: (message: string) => void
}

export interface UseAgentRunResult {
  phase: AgentRunPhase
  run: AgentRun | null
  /** 事件流连接状态（reconnecting 时页面提示重连中） */
  streamStatus: AgentStreamStatus | null
  error: string | null
  /** 发起一轮对话（内部保证会话 + run + 订阅；失败经 onError 上报，不抛出） */
  send: (text: string) => Promise<void>
  /** 取消当前 run；成功返回 null，失败返回中文文案（同一 run 只发一次请求） */
  cancel: () => Promise<string | null>
  /** 复位（keepSession=true 保留会话上下文，仅清空本轮状态） */
  reset: (options?: { keepSession?: boolean }) => void
}

function buildSessionTitle(text: string): string {
  const normalized = text.trim().replace(/\s+/g, ' ')
  if (normalized.length <= SESSION_TITLE_MAX_LENGTH) return normalized
  return `${normalized.slice(0, SESSION_TITLE_MAX_LENGTH)}…`
}

/** 幂等键（§9.2）：同一轮发送的重试复用同一键，避免后端重复执行写操作 */
function buildIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `agent-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function useAgentRun(handlers: UseAgentRunHandlers = {}): UseAgentRunResult {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const [phase, setPhaseState] = useState<AgentRunPhase>(AGENT_RUN_PHASE.IDLE)
  const [run, setRunState] = useState<AgentRun | null>(null)
  const [streamStatus, setStreamStatus] = useState<AgentStreamStatus | null>(null)
  const [error, setErrorState] = useState<string | null>(null)

  const phaseRef = useRef<AgentRunPhase>(AGENT_RUN_PHASE.IDLE)
  const runRef = useRef<AgentRun | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  const unsubscribeRef = useRef<(() => void) | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const reconcileTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** 轮次令牌：新发送 / 复位后旧异步结果一律丢弃 */
  const tokenRef = useRef(0)
  /** 是否有一轮 run 在办（防重复发送） */
  const activeRef = useRef(false)
  /** 取消请求已发出（同一 run 防重复） */
  const cancelRequestedRef = useRef(false)
  /** 续传游标与去重水位 */
  const lastEventIdRef = useRef<string | null>(null)
  const lastSequenceRef = useRef(-1)
  const lastDeltaSequenceRef = useRef<Map<string, number>>(new Map())

  const setPhase = useCallback((next: AgentRunPhase) => {
    phaseRef.current = next
    setPhaseState(next)
    handlersRef.current.onPhaseChange?.(next)
  }, [])

  const setRun = useCallback((next: AgentRun | null) => {
    runRef.current = next
    setRunState(next)
  }, [])

  const clearReconcileTimer = useCallback(() => {
    if (reconcileTimerRef.current) {
      clearTimeout(reconcileTimerRef.current)
      reconcileTimerRef.current = null
    }
  }, [])

  const closeStream = useCallback(() => {
    unsubscribeRef.current?.()
    unsubscribeRef.current = null
    abortRef.current?.abort()
    abortRef.current = null
    clearReconcileTimer()
  }, [clearReconcileTimer])

  const failRun = useCallback(
    (message: string) => {
      setErrorState(message)
      setPhase(AGENT_RUN_PHASE.ERROR)
      activeRef.current = false
      handlersRef.current.onError?.(message)
      closeStream()
    },
    [closeStream, setPhase]
  )

  const finishRun = useCallback(
    (status: AgentRunStatus, message?: string) => {
      setRun(
        runRef.current
          ? {
              ...runRef.current,
              status,
              error: message ?? runRef.current.error,
              finishedAt: new Date().toISOString(),
            }
          : runRef.current
      )
      setPhase(AGENT_RUN_PHASE.FINISHED)
      activeRef.current = false
      closeStream()
    },
    [closeStream, setPhase, setRun]
  )

  /**
   * 补发终态事件：取消快照 / 发起即终态时，服务端 run_finished 可能不经过本连接，
   * 页面消息态需要同一路事件驱动（sequence 取本地水位 +1，重连回放仍走去重）。
   */
  const emitSyntheticFinished = useCallback(
    (run: AgentRun, status: AgentRunStatus, message?: string) => {
      const event: AgentRunEvent = {
        type: AGENT_EVENT_TYPE.RUN_FINISHED,
        runId: run.id,
        sequence: lastSequenceRef.current + 1,
        timestamp: new Date().toISOString(),
        status,
        error: message,
      }
      lastSequenceRef.current = event.sequence
      lastEventIdRef.current = String(event.sequence)
      handlersRef.current.onEvent?.(event)
    },
    []
  )

  const handleEvent = useCallback(
    (event: AgentRunEvent) => {
      const isRecoverableInterrupt =
        event.type === AGENT_EVENT_TYPE.ERROR && event.recoverable === true
      // 全局 sequence 单调去重：重连回放时跳过已渲染事件。
      // 网关合成的上游中断帧 id 取「已下发水位」，恰好等于水位，必须放行，
      // 否则用户既看不到中断提示、也只剩静默重连（INT-2520 P2-2）。
      if (event.sequence <= lastSequenceRef.current && !isRecoverableInterrupt) return
      if (event.type === AGENT_EVENT_TYPE.MESSAGE_DELTA) {
        // message_id 维度去重：同一 message 的增量按 sequence 只应用一次
        const applied = lastDeltaSequenceRef.current.get(event.messageId) ?? -1
        if (event.sequence <= applied) return
        lastDeltaSequenceRef.current.set(event.messageId, event.sequence)
      }
      lastSequenceRef.current = event.sequence
      lastEventIdRef.current = String(event.sequence)

      handlersRef.current.onEvent?.(event)

      if (event.type === AGENT_EVENT_TYPE.RUN_FINISHED) {
        finishRun(event.status, event.error)
        return
      }
      if (event.type === AGENT_EVENT_TYPE.ERROR) {
        if (isRecoverableInterrupt) {
          // 可恢复的上游中断：不关流、不进终态，只提示「连接中断，正在重连…」，
          // 由 SSE 层按 Last-Event-ID 续传（游标仍取已确认水位）。
          if (phaseRef.current !== AGENT_RUN_PHASE.CANCELLING) {
            setPhase(AGENT_RUN_PHASE.RECONNECTING)
          }
          return
        }
        failRun(event.errorMessage || AGENT_ERROR_COPY.runFailed)
        return
      }
      if (event.type === AGENT_EVENT_TYPE.RUN_STARTED) {
        setRun(runRef.current ? { ...runRef.current, status: event.status } : runRef.current)
      }
    },
    [failRun, finishRun, setPhase, setRun]
  )

  const openStream = useCallback(
    (runId: string, token: number) => {
      closeStream()
      const controller = new AbortController()
      abortRef.current = controller
      unsubscribeRef.current = subscribeAgentRunEvents(runId, {
        lastEventId: lastEventIdRef.current,
        signal: controller.signal,
        onStatus: (status) => {
          if (token !== tokenRef.current) return
          setStreamStatus(status)
          if (status === AGENT_STREAM_STATUS.RECONNECTING) {
            setPhase(AGENT_RUN_PHASE.RECONNECTING)
          } else if (
            status === AGENT_STREAM_STATUS.OPEN &&
            phaseRef.current !== AGENT_RUN_PHASE.CANCELLING
          ) {
            setPhase(AGENT_RUN_PHASE.RUNNING)
          }
        },
        onEvent: (event) => {
          if (token !== tokenRef.current) return
          handleEvent(event)
        },
        onFailure: (message) => {
          if (token !== tokenRef.current) return
          failRun(message)
        },
      })
    },
    [closeStream, failRun, handleEvent, setPhase]
  )

  const send = useCallback(
    async (text: string) => {
      if (activeRef.current) return
      const token = tokenRef.current + 1
      tokenRef.current = token
      activeRef.current = true
      cancelRequestedRef.current = false
      lastEventIdRef.current = null
      lastSequenceRef.current = -1
      lastDeltaSequenceRef.current.clear()
      setErrorState(null)
      setStreamStatus(null)
      setPhase(AGENT_RUN_PHASE.PREPARING)

      try {
        let sessionId = sessionIdRef.current
        if (!sessionId) {
          const session = await createAgentSession({ title: buildSessionTitle(text) })
          if (token !== tokenRef.current) return
          sessionId = session.id
          sessionIdRef.current = sessionId
        }

        const run = await createAgentRun(sessionId, { message: text }, buildIdempotencyKey())
        if (token !== tokenRef.current) return
        setRun(run)

        if (isTerminalRunStatus(run.status)) {
          emitSyntheticFinished(run, run.status, run.error)
          finishRun(run.status, run.error)
          return
        }
        setPhase(AGENT_RUN_PHASE.RUNNING)
        openStream(run.id, token)
      } catch (err) {
        if (token !== tokenRef.current) return
        failRun(toAgentErrorMessage(err))
      }
    },
    [emitSyntheticFinished, failRun, finishRun, openStream, setPhase, setRun]
  )

  const cancel = useCallback(async (): Promise<string | null> => {
    const current = runRef.current
    if (!current || cancelRequestedRef.current) return null
    cancelRequestedRef.current = true
    setPhase(AGENT_RUN_PHASE.CANCELLING)
    const token = tokenRef.current

    try {
      const snapshot = await cancelAgentRun(current.id)
      if (token !== tokenRef.current) return null
      if (snapshot) setRun(snapshot)
      if (snapshot && isTerminalRunStatus(snapshot.status)) {
        emitSyntheticFinished(snapshot, snapshot.status, snapshot.error)
        finishRun(snapshot.status, snapshot.error)
        return null
      }
      // 服务端已接受，但终态事件可能尚未推送：短暂核对 run 快照，避免界面卡在 CANCELLING
      clearReconcileTimer()
      reconcileTimerRef.current = setTimeout(() => {
        void (async () => {
          if (token !== tokenRef.current) return
          try {
            const latest = await getAgentRun(current.id)
            if (token !== tokenRef.current) return
            setRun(latest)
            if (isTerminalRunStatus(latest.status)) {
              emitSyntheticFinished(latest, latest.status, latest.error)
              finishRun(latest.status, latest.error)
            } else {
              setPhase(AGENT_RUN_PHASE.RUNNING)
            }
          } catch {
            if (token !== tokenRef.current) return
            setPhase(AGENT_RUN_PHASE.RUNNING)
          }
        })()
      }, CANCEL_RECONCILE_DELAY_MS)
      return null
    } catch (err) {
      if (token !== tokenRef.current) return null
      cancelRequestedRef.current = false
      setPhase(AGENT_RUN_PHASE.RUNNING)
      const message = toAgentErrorMessage(err)
      setErrorState(message)
      return message
    }
  }, [clearReconcileTimer, emitSyntheticFinished, finishRun, setPhase, setRun])

  const reset = useCallback(
    (options?: { keepSession?: boolean }) => {
      tokenRef.current += 1
      activeRef.current = false
      cancelRequestedRef.current = false
      lastEventIdRef.current = null
      lastSequenceRef.current = -1
      lastDeltaSequenceRef.current.clear()
      closeStream()
      setRun(null)
      setErrorState(null)
      setStreamStatus(null)
      if (!options?.keepSession) sessionIdRef.current = null
      setPhase(AGENT_RUN_PHASE.IDLE)
    },
    [closeStream, setPhase, setRun]
  )

  // 卸载：断开流与定时器（不 setState）
  useEffect(() => {
    return () => {
      tokenRef.current += 1
      unsubscribeRef.current?.()
      unsubscribeRef.current = null
      abortRef.current?.abort()
      abortRef.current = null
      if (reconcileTimerRef.current) clearTimeout(reconcileTimerRef.current)
    }
  }, [])

  return { phase, run, streamStatus, error, send, cancel, reset }
}
