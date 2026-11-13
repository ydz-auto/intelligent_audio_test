/**
 * 平台 Agent run 会话（application 层单一实例；INT-2507）。
 *
 * 整页（/ai-chat）与全局浮窗（AgentWorkbench）是两个宿主，但平台 Agent 只有一个服务端
 * 会话（doc/agent化/07_单Agent_Skills落地方案.md §9/§11/§12.2）。INT-2507 之前，会话 id
 * 与 run 生命周期挂在各自宿主的 useAgentRun 组件 ref 上：
 * - 浮窗「展开整页」= 浮窗卸载 → session_id 随之丢失，整页按新会话提问，Agent「忘了上文」；
 * - 刷新同理，且没有任何恢复路径（getAgentSession 已实现但无调用点）；
 * - 浮窗与整页同时在 /ai-chat 时可各发一条 run，两条 run 各写各的 assistant 气泡到同一份
 *   消息列表，停止 / 取消只作用于发起侧。
 *
 * 本模块把 run 生命周期收敛为模块级单一实例：
 * - 会话 id / 最近 run id 落在 aiChatSessionStore 并随 config/messages 持久化（换宿主与刷新后
 *   都续用同一服务端会话）；
 * - phase / run / streamStatus / 错误归一 / 取消闸唯一，两个宿主订阅同一份状态：一侧正在跑时
 *   另一侧输入区同样禁用，停止钮只对当前 run 生效，同页不会再并发两条 run；
 * - 事件 → 消息补丁只在这里做一次（直接写共享消息列表），两套补丁器重复拼接正文的问题消失；
 * - 宿主挂载时若已有会话且无进行中 run，用 getAgentSession 校验 / 恢复：服务端会话不存在则
 *   清掉本地会话 id（下次发送新建，避免反复续用失效会话）；本地消息为空时用服务端历史回填；
 *   刷新打断的悬挂 assistant 气泡按服务端最新 run 状态收口。
 *
 * 已知边界（本轮不做）：刷新时若 run 仍在服务端执行，本端不重接 SSE（事件游标未持久化），
 * 该轮气泡按「事件流中断」收口；服务端会话上下文不受影响，下一轮追问仍延续同一会话。
 */
import { create } from 'zustand'
import { toast } from 'sonner'

import {
  AGENT_ERROR_COPY,
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_LABELS,
  isTerminalRunStatus,
  type AgentRun,
  type AgentRunEvent,
  type AgentRunStatus,
  type AgentSessionMessage,
} from '@/domain/models/agent'
import {
  CHAT_MESSAGE_STATUS,
  type ChatMessage,
  type ChatMessageStatus,
} from '@/domain/models/aiChat'
import {
  AGENT_STREAM_STATUS,
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  getAgentRun,
  getAgentSession,
  subscribeAgentRunEvents,
  toAgentErrorMessage,
  type AgentStreamStatus,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'

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

/**
 * 平台 Agent run 的宿主：整页 `/ai-chat`（page）与全局浮窗（workbench）可同时挂载，
 * INT-2507 之后两者订阅同一份 store。
 */
export type AgentRunHostKind = 'page' | 'workbench'

/**
 * 宿主离场语义（INT-2521 按 A5–A7 收窄）：
 * - `cancel`：浮窗「关闭」、离开 `/ai-chat` 路由 —— 用户明确结束这一侧；
 * - `keep`：浮窗「最小化」「展开整页」、整页 ↔ 浮窗切换 —— 只是宿主暂时卸载，run 应继续。
 */
export type AgentRunHostDetachReason = 'cancel' | 'keep'

/**
 * 宿主离场中断进行中回答时的用户提示（INT-2521 文案，按 A5 收窄口径：
 * 最小化 / 展开整页不再中断，只有关闭浮窗与离开页面会结束进行中的对话）。
 */
export const AGENT_RUN_UNMOUNT_CANCEL_COPY =
  '已中断当前回答：关闭浮窗或离开当前页面会结束进行中的对话'

/**
 * 宿主离场时仍需中止服务端 run 的阶段（INT-2521）：idle / cancelling / finished / error
 * 没有在办 run，发取消只会打空。
 */
const IN_FLIGHT_PHASES: readonly AgentRunPhase[] = [
  AGENT_RUN_PHASE.PREPARING,
  AGENT_RUN_PHASE.RUNNING,
  AGENT_RUN_PHASE.RECONNECTING,
]

/**
 * 最后一个宿主离场后的宽限（ms）：切换形态 / StrictMode `mount → cleanup → mount` 会
 * 让宿主瞬时全卸再挂，同一提交内重新登记即视为未离场，不取消在办 run。
 */
const HOST_DETACH_GRACE_MS = 0

/** 是否有一轮 run 在办（输入区禁用 / 停止钮可用的唯一判据，两宿主同口径） */
export function isAgentRunActive(phase: AgentRunPhase): boolean {
  return (
    phase === AGENT_RUN_PHASE.PREPARING ||
    phase === AGENT_RUN_PHASE.RUNNING ||
    phase === AGENT_RUN_PHASE.RECONNECTING ||
    phase === AGENT_RUN_PHASE.CANCELLING
  )
}

/** 取消后若服务端未推 run_finished，延迟核对 run 快照（ms） */
const CANCEL_RECONCILE_DELAY_MS = 2_000

/** 会话标题取首条消息前若干字符（后端缺省时也可自行生成，便于会话列表识别） */
const SESSION_TITLE_MAX_LENGTH = 32

/** 消息补丁时用于判定的「进行中」状态集合（刷新中断的悬挂气泡据它定位） */
const IN_FLIGHT_MESSAGE_STATUSES: ReadonlySet<ChatMessageStatus> = new Set([
  CHAT_MESSAGE_STATUS.LOADING,
  CHAT_MESSAGE_STATUS.STREAMING,
])

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

function buildLoadingMessage(key: string): ChatMessage {
  const now = Date.now()
  return {
    key,
    from: 'assistant',
    versions: [{ id: `${key}-v1`, content: '' }],
    createdAt: now,
    startedAt: now,
    status: CHAT_MESSAGE_STATUS.LOADING,
  }
}

/** run 终态 → 消息状态补丁（保留已生成正文，仅标终态徽标） */
function toTerminalPatch(
  status: AgentRunStatus,
  startedAt: number | undefined,
  now: number
): Partial<ChatMessage> {
  return {
    status: CHAT_MESSAGE_STATUS.COMPLETE,
    runStatus: status,
    completedAt: now,
    durationMs: startedAt ? now - startedAt : 0,
    isReasoningStreaming: false,
  }
}

/** 服务端会话历史 → 对话消息（仅在本地消息为空时回填；role 只认 user / assistant） */
function toRestoredMessages(messages: AgentSessionMessage[]): ChatMessage[] {
  return messages
    .filter(
      (message) =>
        (message.role === 'user' || message.role === 'assistant') &&
        message.content.trim() !== ''
    )
    .map((message, index) => ({
      key: `restored-${index}`,
      from: message.role === 'user' ? ('user' as const) : ('assistant' as const),
      versions: [
        { id: `restored-${index}-v1`, content: message.content },
      ],
      status: CHAT_MESSAGE_STATUS.COMPLETE,
    }))
}

export interface SendAgentRunOptions {
  /** 是否追加本轮 user 消息（重新生成=原指令已在截断数组内，只补 assistant 占位） */
  appendUserMessage?: boolean
}

type AgentRunStoreState = {
  phase: AgentRunPhase
  run: AgentRun | null
  /** 事件流连接状态（reconnecting 时页面提示重连中） */
  streamStatus: AgentStreamStatus | null
  error: string | null
  /** 发起一轮对话（内部保证会话 + run + 订阅；失败落 error 态，不抛出） */
  send: (text: string, options?: SendAgentRunOptions) => Promise<void>
  /** 取消当前 run；成功返回 null，失败返回中文文案（同一 run 只发一次请求） */
  cancel: () => Promise<string | null>
  /** 复位（keepSession=true 保留会话上下文，仅清空本轮状态） */
  reset: (options?: { keepSession?: boolean }) => void
  /**
   * 宿主挂载时的恢复（幂等）：有会话 id 且无进行中 run 时用 getAgentSession 校验 / 回填 /
   * 收口刷新打断的气泡。会话已失效（404/410）则清掉本地会话 id。
   */
  restore: () => Promise<void>
  /** 宿主登记（整页 / 浮窗；同 kind 多次挂载按一次计） */
  attachHost: (host: AgentRunHostKind) => void
  /**
   * 宿主注销（INT-2521 收窄）：只有最后一个宿主按 `cancel` 语义离场才中止在办 run；
   * `keep`（最小化 / 展开整页 / 切换形态）不动 run。宽限窗口内重新登记则视为未离场。
   */
  detachHost: (host: AgentRunHostKind, reason?: AgentRunHostDetachReason) => void
}

export const useAgentRunStore = create<AgentRunStoreState>()((set, get) => {
  // ===== 非渲染态控制器字段（模块单一实例；两宿主共享） =====
  /** 轮次令牌：新发送 / 复位后旧异步结果一律丢弃 */
  let token = 0
  /** 是否有一轮 run 在办（防两宿主并发发送） */
  let active = false
  /** 取消请求已发出（同一 run 防重复） */
  let cancelRequested = false
  let streamClose: (() => void) | null = null
  let streamAbort: AbortController | null = null
  let reconcileTimer: ReturnType<typeof setTimeout> | null = null
  /** 续传游标与去重水位 */
  let lastEventId: string | null = null
  let lastSequence = -1
  const lastDeltaSequences = new Map<string, number>()
  /** 当前 assistant 气泡 key 与已累积正文（事件补丁的唯一写入点） */
  let assistantKey: string | null = null
  let assistantContent = ''
  /** 已恢复校验过的会话 id（同会话只查一次 getAgentSession） */
  let restoredSessionId: string | null = null
  let restoreInFlight: Promise<void> | null = null
  /** 已登记存活的宿主（整页 / 浮窗）：只有最后一个宿主离场才中止在办 run */
  const attachedHosts = new Set<AgentRunHostKind>()
  let hostDetachTimer: ReturnType<typeof setTimeout> | null = null
  /** 最后一个宿主按 cancel 语义离场时建 run 请求仍在途：响应返回后补发取消（INT-2521） */
  let detachCancelPending = false

  const session = () => useAiChatSession.getState()

  const setPhase = (phase: AgentRunPhase) => set({ phase })

  const closeStream = () => {
    streamClose?.()
    streamClose = null
    streamAbort?.abort()
    streamAbort = null
    if (reconcileTimer) {
      clearTimeout(reconcileTimer)
      reconcileTimer = null
    }
  }

  /**
   * 最后一个宿主已按取消语义离场（INT-2521）：在办的 run 没人接收结果，通知服务端取消。
   * fire-and-forget（失败只记日志），但走 `cancel()` 的同一取消闸与终态收口，
   * 保证「全局只发一次 cancelAgentRun」且消息列表里的气泡落可读终态。
   */
  const abandonInFlightRun = () => {
    const { phase, run } = get()
    if (!IN_FLIGHT_PHASES.includes(phase)) return
    if (run && !isTerminalRunStatus(run.status)) {
      const runId = run.id
      toast.info(AGENT_RUN_UNMOUNT_CANCEL_COPY)
      void get()
        .cancel()
        .then((failure) => {
          if (failure) {
            console.warn('[agent] 宿主离场时取消 run 失败', runId, failure)
          }
        })
      return
    }
    // 建 run 请求仍在途（PREPARING 且 run 尚未落库）：响应返回后补发取消，不留孤儿 run
    detachCancelPending = true
  }

  const attachHost = (host: AgentRunHostKind) => {
    attachedHosts.add(host)
    // 宽限窗口内重新登记 = 切换形态 / StrictMode 双挂载，不算离场
    if (hostDetachTimer) {
      clearTimeout(hostDetachTimer)
      hostDetachTimer = null
    }
  }

  const detachHost = (
    host: AgentRunHostKind,
    reason: AgentRunHostDetachReason = 'keep'
  ) => {
    attachedHosts.delete(host)
    if (reason !== 'cancel') return
    if (hostDetachTimer) return
    hostDetachTimer = setTimeout(() => {
      hostDetachTimer = null
      if (attachedHosts.size > 0) return
      abandonInFlightRun()
    }, HOST_DETACH_GRACE_MS)
  }

  /** 只补当前 run 的 assistant 气泡（消息列表两宿主共享，补丁只做一次） */
  const patchAssistant = (
    updater: (message: ChatMessage) => ChatMessage
  ) => {
    const key = assistantKey
    if (!key) return
    session().updateMessages((prev) =>
      prev.map((message) => (message.key === key ? updater(message) : message))
    )
  }

  const finishRun = (status: AgentRunStatus, message?: string) => {
    const current = get().run
    set({
      run: current
        ? {
            ...current,
            status,
            error: message ?? current.error,
            finishedAt: new Date().toISOString(),
          }
        : current,
      phase: AGENT_RUN_PHASE.FINISHED,
    })
    active = false
    session().setAgentRunId(null)
    closeStream()
  }

  const failRun = (message: string) => {
    patchAssistant((current) => ({
      ...current,
      status: CHAT_MESSAGE_STATUS.ERROR,
      errorCode: 'AGENT_ERROR',
      versions: [
        {
          id: current.versions[0]?.id ?? `${current.key}-v1`,
          content: message,
        },
      ],
      completedAt: Date.now(),
      durationMs: current.startedAt ? Date.now() - current.startedAt : 0,
    }))
    assistantKey = null
    set({ error: message, phase: AGENT_RUN_PHASE.ERROR })
    active = false
    session().setAgentRunId(null)
    closeStream()
  }

  /** 事件 → 消息 / 状态补丁（去重后调用） */
  const applyEvent = (event: AgentRunEvent) => {
    switch (event.type) {
      case AGENT_EVENT_TYPE.MESSAGE_DELTA: {
        assistantContent += event.delta
        const content = assistantContent
        patchAssistant((message) => ({
          ...message,
          status: CHAT_MESSAGE_STATUS.STREAMING,
          startedAt: message.startedAt ?? Date.now(),
          versions: [
            { id: message.versions[0]?.id ?? `${message.key}-v1`, content },
          ],
        }))
        return
      }
      case AGENT_EVENT_TYPE.TOOL_CALL: {
        patchAssistant((message) => {
          const existing = message.toolCalls ?? []
          const call = {
            id: event.toolCallId,
            tool: event.tool,
            label: AGENT_TOOL_LABELS[event.tool] ?? event.tool,
            status: 'running' as const,
            summary: event.summary,
          }
          const next = existing.some((item) => item.id === call.id)
            ? existing.map((item) =>
                item.id === call.id ? { ...item, ...call } : item
              )
            : [...existing, call]
          return { ...message, toolCalls: next }
        })
        return
      }
      case AGENT_EVENT_TYPE.TOOL_RESULT: {
        patchAssistant((message) => ({
          ...message,
          toolCalls: (message.toolCalls ?? []).map((call) =>
            call.id === event.toolCallId
              ? {
                  ...call,
                  status:
                    event.status === 'SUCCEEDED'
                      ? ('completed' as const)
                      : ('error' as const),
                  summary: event.summary ?? call.summary,
                  errorCode: event.errorCode,
                  sourceRefs: event.sourceRefs ?? call.sourceRefs,
                }
              : call
          ),
        }))
        return
      }
      case AGENT_EVENT_TYPE.RUN_FINISHED: {
        const now = Date.now()
        patchAssistant((message) =>
          message.versions[0]?.content || assistantContent
            ? {
                ...message,
                ...toTerminalPatch(event.status, message.startedAt, now),
              }
            : {
                ...message,
                ...toTerminalPatch(event.status, message.startedAt, now),
                versions: [
                  {
                    id: message.versions[0]?.id ?? `${message.key}-v1`,
                    content:
                      event.status === AGENT_RUN_STATUS.CANCELLED
                        ? AGENT_ERROR_COPY.cancelled
                        : event.error || AGENT_ERROR_COPY.runFailed,
                  },
                ],
              }
        )
        assistantKey = null
        finishRun(event.status, event.error)
        return
      }
      case AGENT_EVENT_TYPE.ERROR: {
        failRun(event.errorMessage || AGENT_ERROR_COPY.runFailed)
        return
      }
      case AGENT_EVENT_TYPE.RUN_STARTED: {
        const current = get().run
        if (current) set({ run: { ...current, status: event.status } })
        return
      }
      default:
        // approval_required（M2）/ context_compacted：不改变消息正文
        return
    }
  }

  /** 全局 sequence 单调去重：重连回放不会重复渲染同一段文本 */
  const handleEvent = (event: AgentRunEvent) => {
    if (event.sequence <= lastSequence) return
    if (event.type === AGENT_EVENT_TYPE.MESSAGE_DELTA) {
      const applied = lastDeltaSequences.get(event.messageId) ?? -1
      if (event.sequence <= applied) return
      lastDeltaSequences.set(event.messageId, event.sequence)
    }
    lastSequence = event.sequence
    lastEventId = String(event.sequence)
    applyEvent(event)
  }

  /**
   * 补发终态事件：取消快照 / 发起即终态时，服务端 run_finished 可能不经过本连接，
   * 页面消息态需要同一路事件驱动（sequence 取本地水位 +1，重连回放仍走去重）。
   */
  const emitSyntheticFinished = (
    run: AgentRun,
    status: AgentRunStatus,
    message?: string
  ) => {
    const event: AgentRunEvent = {
      type: AGENT_EVENT_TYPE.RUN_FINISHED,
      runId: run.id,
      sequence: lastSequence + 1,
      timestamp: new Date().toISOString(),
      status,
      error: message,
    }
    lastSequence = event.sequence
    lastEventId = String(event.sequence)
    applyEvent(event)
  }

  const openStream = (runId: string, runToken: number) => {
    closeStream()
    const controller = new AbortController()
    streamAbort = controller
    streamClose = subscribeAgentRunEvents(runId, {
      lastEventId,
      signal: controller.signal,
      onStatus: (status) => {
        if (runToken !== token) return
        set({ streamStatus: status })
        if (status === AGENT_STREAM_STATUS.RECONNECTING) {
          setPhase(AGENT_RUN_PHASE.RECONNECTING)
        } else if (
          status === AGENT_STREAM_STATUS.OPEN &&
          get().phase !== AGENT_RUN_PHASE.CANCELLING
        ) {
          setPhase(AGENT_RUN_PHASE.RUNNING)
        }
      },
      onEvent: (event) => {
        if (runToken !== token) return
        handleEvent(event)
      },
      onFailure: (message) => {
        if (runToken !== token) return
        failRun(message)
      },
    })
  }

  const send = async (text: string, options?: SendAgentRunOptions) => {
    if (active) return
    const appendUserMessage = options?.appendUserMessage ?? true
    const runToken = token + 1
    token = runToken
    active = true
    cancelRequested = false
    lastEventId = null
    lastSequence = -1
    lastDeltaSequences.clear()
    assistantContent = ''
    set({ error: null, streamStatus: null, phase: AGENT_RUN_PHASE.PREPARING })

    // user 气泡 + assistant 占位落共享消息列表：两宿主读同一份，切换形态不丢
    const userKey = `user-${Date.now()}`
    const assistantMessageKey = `assistant-${Date.now()}`
    assistantKey = assistantMessageKey
    const userMessage: ChatMessage = {
      key: userKey,
      from: 'user',
      versions: [{ id: `${userKey}-v1`, content: text }],
      createdAt: Date.now(),
    }
    const loadingMessage = buildLoadingMessage(assistantMessageKey)
    session().updateMessages((prev) => [
      ...(appendUserMessage ? [...prev, userMessage] : prev),
      loadingMessage,
    ])

    try {
      let sessionId = session().agentSessionId
      if (!sessionId) {
        const created = await createAgentSession({
          title: buildSessionTitle(text),
        })
        if (runToken !== token) return
        sessionId = created.id
        session().setAgentSession(sessionId)
        // 刚建的会话无需再向服务端校验历史
        restoredSessionId = sessionId
      }

      const run = await createAgentRun(
        sessionId,
        { message: text },
        buildIdempotencyKey()
      )
      if (runToken !== token) return
      set({ run })
      session().setAgentRunId(run.id)

      if (detachCancelPending) {
        // 建 run 在途时最后一个宿主已按取消语义离场：补发取消，不进事件流（INT-2521）
        detachCancelPending = false
        if (!isTerminalRunStatus(run.status)) {
          toast.info(AGENT_RUN_UNMOUNT_CANCEL_COPY)
          void get()
            .cancel()
            .then((failure) => {
              if (failure) {
                console.warn('[agent] 宿主离场时取消 run 失败', run.id, failure)
              }
            })
          return
        }
      }

      if (isTerminalRunStatus(run.status)) {
        emitSyntheticFinished(run, run.status, run.error)
        finishRun(run.status, run.error)
        return
      }
      setPhase(AGENT_RUN_PHASE.RUNNING)
      openStream(run.id, runToken)
    } catch (err) {
      if (runToken !== token) return
      failRun(toAgentErrorMessage(err))
    }
  }

  const cancel = async (): Promise<string | null> => {
    const current = get().run
    if (!current || cancelRequested) return null
    cancelRequested = true
    setPhase(AGENT_RUN_PHASE.CANCELLING)
    const runToken = token

    try {
      const snapshot = await cancelAgentRun(current.id)
      if (runToken !== token) return null
      if (snapshot) set({ run: snapshot })
      if (snapshot && isTerminalRunStatus(snapshot.status)) {
        emitSyntheticFinished(snapshot, snapshot.status, snapshot.error)
        finishRun(snapshot.status, snapshot.error)
        return null
      }
      // 服务端已接受，但终态事件可能尚未推送：短暂核对 run 快照，避免界面卡在 CANCELLING
      if (reconcileTimer) clearTimeout(reconcileTimer)
      reconcileTimer = setTimeout(() => {
        void (async () => {
          if (runToken !== token) return
          try {
            const latest = await getAgentRun(current.id)
            if (runToken !== token) return
            set({ run: latest })
            if (isTerminalRunStatus(latest.status)) {
              emitSyntheticFinished(latest, latest.status, latest.error)
              finishRun(latest.status, latest.error)
            } else {
              setPhase(AGENT_RUN_PHASE.RUNNING)
            }
          } catch {
            if (runToken !== token) return
            setPhase(AGENT_RUN_PHASE.RUNNING)
          }
        })()
      }, CANCEL_RECONCILE_DELAY_MS)
      return null
    } catch (err) {
      if (runToken !== token) return null
      cancelRequested = false
      setPhase(AGENT_RUN_PHASE.RUNNING)
      const message = toAgentErrorMessage(err)
      set({ error: message })
      return message
    }
  }

  const reset = (options?: { keepSession?: boolean }) => {
    token += 1
    active = false
    cancelRequested = false
    detachCancelPending = false
    if (hostDetachTimer) {
      clearTimeout(hostDetachTimer)
      hostDetachTimer = null
    }
    lastEventId = null
    lastSequence = -1
    lastDeltaSequences.clear()
    closeStream()
    assistantKey = null
    assistantContent = ''
    restoredSessionId = null
    set({
      run: null,
      error: null,
      streamStatus: null,
      phase: AGENT_RUN_PHASE.IDLE,
    })
    if (!options?.keepSession) {
      session().setAgentSession(null)
      session().setAgentRunId(null)
    }
  }

  /** 本地消息为空时用服务端历史回填（并发发送过则不再覆盖） */
  const hydrateRestoredMessages = (messages: AgentSessionMessage[]) => {
    const restored = toRestoredMessages(messages)
    if (restored.length === 0) return
    session().updateMessages((prev) => (prev.length > 0 ? prev : restored))
  }

  /**
   * 刷新打断的悬挂气泡收口：本地仍有 loading/streaming 的 assistant 气泡，但本端已无进行中
   * run（刷新丢失事件流）。按服务端最新 run 状态给终态；服务端仍在跑则该轮按事件流中断收口。
   */
  const reconcileInterruptedMessage = (runs: AgentRun[]) => {
    const pending = [...session().messages]
      .reverse()
      .find(
        (message) =>
          message.from === 'assistant' &&
          message.status !== undefined &&
          IN_FLIGHT_MESSAGE_STATUSES.has(message.status)
      )
    if (!pending) return
    // 服务端仍有未终态的 run 时它才是这条悬挂气泡对应的那一轮；否则取最近一条
    const latestRun =
      runs.find((run) => !isTerminalRunStatus(run.status)) ??
      runs[runs.length - 1]
    const patch = (message: ChatMessage): ChatMessage => {
      if (latestRun && isTerminalRunStatus(latestRun.status)) {
        return {
          ...message,
          ...toTerminalPatch(latestRun.status, message.startedAt, Date.now()),
          versions:
            message.versions[0]?.content
              ? message.versions
              : [
                  {
                    id: message.versions[0]?.id ?? `${message.key}-v1`,
                    content:
                      latestRun.status === AGENT_RUN_STATUS.CANCELLED
                        ? AGENT_ERROR_COPY.cancelled
                        : latestRun.error || AGENT_ERROR_COPY.runFailed,
                  },
                ],
        }
      }
      return {
        ...message,
        status: CHAT_MESSAGE_STATUS.ERROR,
        errorCode: 'STREAM_INTERRUPTED',
        versions: [
          {
            id: message.versions[0]?.id ?? `${message.key}-v1`,
            content: AGENT_ERROR_COPY.streamFailed,
          },
        ],
        completedAt: Date.now(),
        durationMs: message.startedAt ? Date.now() - message.startedAt : 0,
      }
    }
    session().updateMessages((prev) =>
      prev.map((message) => (message.key === pending.key ? patch(message) : message))
    )
  }

  /**
   * 宿主挂载恢复（幂等）：整页 / 浮窗切换与刷新都会调用。只在没有进行中 run 时校验服务端会话，
   * 不会打断正在流式输出的 run。
   */
  const restore = async (): Promise<void> => {
    if (active) return
    const sessionId = session().agentSessionId
    if (!sessionId) return
    if (restoredSessionId === sessionId) return
    if (restoreInFlight) return restoreInFlight
    const runToken = token
    const promise = (async () => {
      try {
        const detail = await getAgentSession(sessionId)
        if (runToken !== token) return
        if (session().agentSessionId !== sessionId) return
        restoredSessionId = sessionId
        hydrateRestoredMessages(detail.messages)
        reconcileInterruptedMessage(detail.runs)
      } catch (err) {
        if (runToken !== token) return
        if (session().agentSessionId !== sessionId) return
        // 服务端会话已被清理：丢掉本地会话 id，下次发送新建（避免反复续用失效会话）
        if (
          err instanceof ApiError &&
          (err.httpStatus === 404 || err.httpStatus === 410)
        ) {
          restoredSessionId = null
          session().setAgentSession(null)
          session().setAgentRunId(null)
        }
      }
    })()
    restoreInFlight = promise
    void promise.finally(() => {
      if (restoreInFlight === promise) restoreInFlight = null
    })
    return promise
  }

  return {
    phase: AGENT_RUN_PHASE.IDLE,
    run: null,
    streamStatus: null,
    error: null,
    send,
    cancel,
    reset,
    restore,
    attachHost,
    detachHost,
  }
})
