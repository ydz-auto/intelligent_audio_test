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
 * 该轮气泡按「事件流中断」收口；run 停在 WAITING_APPROVAL 且待审批卡已恢复时例外——气泡按
 * 「等待审批」中性收口，不把用户引向重发（INT-2472 审计 P2-1）。服务端会话上下文不受影响，
 * 下一轮追问仍延续同一会话。
 */
import { create } from 'zustand'
import { toast } from 'sonner'

import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_ERROR_CODE,
  AGENT_APPROVAL_STATUS,
  AGENT_AUTO_COPY,
  AGENT_AUTO_ERROR_CODE,
  AGENT_ERROR_COPY,
  AGENT_EVENT_TYPE,
  AGENT_RUN_MODE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_LABELS,
  isPendingApprovalStatus,
  isTerminalRunStatus,
  type AgentApproval,
  type AgentApprovalDecision,
  type AgentAutoPause,
  type AgentAutoProgress,
  type AgentRun,
  type AgentRunBudget,
  type AgentRunEvent,
  type AgentRunInput,
  type AgentRunMode,
  type AgentRunPausePolicy,
  type AgentRunStatus,
  type AgentSessionMessage,
} from '@/domain/models/agent'
import {
  CHAT_MESSAGE_STATUS,
  type ChatMessage,
  type ChatMessageStatus,
} from '@/domain/models/aiChat'
import {
  AGENT_PROVIDER_NOT_CONFIGURED_CODE,
  isProviderNotConfiguredError,
} from '@/domain/models/agentProvider'
import {
  AGENT_STREAM_STATUS,
  cancelAgentRun,
  createAgentRun,
  createAgentSession,
  decideAgentApproval,
  getAgentRun,
  getAgentSession,
  listAgentApprovals,
  resumeAgentRun,
  subscribeAgentRunEvents,
  toAgentErrorMessage,
  type AgentStreamStatus,
} from '@/infrastructure/api/agentApi'
import { ApiError } from '@/infrastructure/api/api-error'
import { useAiChatSession } from '@/infrastructure/stores/aiChatSessionStore'

import {
  appendTimelineEntry,
  applyApprovalToTimeline,
  type AgentTimelineEntry,
} from './agent-timeline'
import {
  autoTerminalKind,
  autoTerminalMessageText,
  isAutoRun,
} from './auto-progress'

/** Run 生命周期阶段（idle 未开始；cancelling 已发取消请求等终态） */
export const AGENT_RUN_PHASE = {
  IDLE: 'idle',
  PREPARING: 'preparing',
  RUNNING: 'running',
  /** 写操作提案待审批（§9.4：run 在服务端 WAITING_APPROVAL，事件流仍开着） */
  WAITING_APPROVAL: 'waiting_approval',
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
  AGENT_RUN_PHASE.WAITING_APPROVAL,
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
    phase === AGENT_RUN_PHASE.WAITING_APPROVAL ||
    phase === AGENT_RUN_PHASE.RECONNECTING ||
    phase === AGENT_RUN_PHASE.CANCELLING
  )
}

/** 取消后若服务端未推 run_finished，延迟核对 run 快照（ms） */
const CANCEL_RECONCILE_DELAY_MS = 2_000

/**
 * 刷新恢复后「继续」：本页没有事件流（游标未持久化、不重接 SSE），改为按快照轮询
 * 服务端终态（INT-2477 UX 审计 P2）。首次 1.5s、之后 5s 一次，终态即停。
 */
const AUTO_TERMINAL_POLL_FIRST_DELAY_MS = 1_500
const AUTO_TERMINAL_POLL_INTERVAL_MS = 5_000
/** 轮询上限：Auto 默认时长预算是 30 分钟，超过后不再空转，提示刷新查看 */
const AUTO_TERMINAL_POLL_MAX_MS = 30 * 60_000
/** 连续取快照失败多少次后停止轮询（网络抖动重试，避免永久空转） */
const AUTO_TERMINAL_POLL_MAX_FAILURES = 4

/**
 * Auto 暂停期间的占位正文（INT-2477 代码审计 P2）：继续 / 终态收口只替换这些，
 * 已流式产出的正文一律保留，终态由 `runStatus` 徽标与进度面板表达。
 */
const AUTO_PAUSE_PLACEHOLDER_CONTENT: ReadonlySet<string> = new Set([
  AGENT_AUTO_COPY.phasePendingResume,
  AGENT_AUTO_COPY.restoredPaused,
  AGENT_AUTO_COPY.restoredResuming,
])

/** 气泡正文是否为空或暂停占位（空正文同样可被占位 / 终态文案填充） */
function isAutoPausePlaceholderContent(content: string | undefined): boolean {
  return (
    content === undefined ||
    content === '' ||
    AUTO_PAUSE_PLACEHOLDER_CONTENT.has(content)
  )
}

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
  /**
   * 运行模式（INT-2474）：缺省 chat。Auto 打开只影响本轮发起，
   * 关掉后普通对话照常（请求体不带 mode / budget）。
   */
  mode?: AgentRunMode
  /** Auto 预算（只能收紧；仅 Auto 模式下发） */
  budget?: AgentRunBudget
}

type AgentRunStoreState = {
  phase: AgentRunPhase
  run: AgentRun | null
  /** 事件流连接状态（reconnecting 时页面提示重连中） */
  streamStatus: AgentStreamStatus | null
  error: string | null
  /** 本 run 的审批单（待审批 + 已决；重连 / 刷新后按服务端列表还原） */
  approvals: AgentApproval[]
  /** 审批列表同步中（重连后显示「正在同步审批状态…」） */
  approvalsLoading: boolean
  /** 审批列表加载失败（中文；面板落错误态并可重试） */
  approvalsError: string | null
  /** 决策请求在途的审批单 id（按钮防重复：同一条只发一次） */
  decidingApprovalIds: string[]
  /** Run 时间线（事件流有序投影；重连回放不重复） */
  timeline: AgentTimelineEntry[]
  /** Auto 最新进度快照（auto_step；非 Auto / 本轮未开始为 null） */
  autoProgress: AgentAutoProgress | null
  /** Auto 暂停事实（run_paused；继续或终态后清空） */
  autoPause: AgentAutoPause | null
  /** Auto 暂停策略（run_started.pause_policy；启动即展示「何时会暂停」） */
  autoPausePolicy: AgentRunPausePolicy | null
  /** 继续请求在途（按钮防连点） */
  resumingAuto: boolean
  /**
   * 刷新恢复后点「继续」：本页无事件流，正在轮询服务端终态（P2）。
   * 面板据此给出「等待服务端结果」而不是无限「正在收集步骤进度」。
   */
  autoTracking: boolean
  /** Auto 暂停后继续（POST /agent/runs/{id}/resume；失败返回中文文案） */
  resumeAuto: () => Promise<string | null>
  /** 发起一轮对话（内部保证会话 + run + 订阅；失败落 error 态，不抛出） */
  send: (text: string, options?: SendAgentRunOptions) => Promise<void>
  /** 取消当前 run；成功返回 null，失败返回中文文案（同一 run 只发一次请求） */
  cancel: () => Promise<string | null>
  /**
   * 审批决策（§9.4）：批准 / 拒绝一条写操作提案。
   * 同一审批单连点只发一次请求；成功返回 null，失败返回卡片可展示的中文文案。
   */
  decideApproval: (
    approvalId: string,
    decision: AgentApprovalDecision,
    /** DESTRUCTIVE 的 APPROVE 必须二次确认（INT-2467）：仅此时传 true */
    confirm?: boolean
  ) => Promise<string | null>
  /**
   * 同步本 run 的审批单（重连 / 恢复 / 决策 409 后）。
   * 服务端列表是权威：已决状态覆盖本地，未在列表中的本地条目保留（不丢待审批卡）。
   */
  refreshApprovals: (options?: {
    runId?: string
    /** 是否按待审批状态切换生命周期阶段（无事件流的恢复场景传 false） */
    syncPhase?: boolean
  }) => Promise<void>
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
  /**
   * 刷新恢复的 Auto 暂停气泡 key：点「继续」后只更新这一条（撤掉暂停占位文案 /
   * 等待审批徽标），终态时同样用它把气泡收口到 Auto 终态（P2）。
   */
  let restoredAutoMessageKey: string | null = null
  /** 刷新恢复后续跑的服务端终态轮询定时器（终态 / 复位 / 新 run 即清） */
  let autoPollTimer: ReturnType<typeof setTimeout> | null = null
  /** 已登记存活的宿主（整页 / 浮窗）：只有最后一个宿主离场才中止在办 run */
  const attachedHosts = new Set<AgentRunHostKind>()
  let hostDetachTimer: ReturnType<typeof setTimeout> | null = null
  /** 最后一个宿主按 cancel 语义离场时建 run 请求仍在途：响应返回后补发取消（INT-2521） */
  let detachCancelPending = false
  /** 决策请求在途的审批单 id（连点防重的唯一闸门；与渲染态 decidingApprovalIds 同步） */
  const decidingApprovals = new Set<string>()
  /** 审批列表请求令牌：复位 / 新一轮后旧响应一律丢弃 */
  let approvalRefreshToken = 0
  /** run 快照请求令牌（终态补 token / 预算消耗，晚到的旧响应不覆盖新 run） */
  let runSnapshotToken = 0
  /** Auto「继续」请求在途（同一暂停点防连点） */
  let resumeRequested = false

  const session = () => useAiChatSession.getState()

  const setPhase = (phase: AgentRunPhase) => set({ phase })

  /** 停掉刷新恢复后的服务端终态轮询（终态 / 复位 / 新 run 都走这里） */
  const clearAutoPolling = () => {
    if (autoPollTimer) {
      clearTimeout(autoPollTimer)
      autoPollTimer = null
    }
  }

  const closeStream = () => {
    streamClose?.()
    streamClose = null
    streamAbort?.abort()
    streamAbort = null
    if (reconcileTimer) {
      clearTimeout(reconcileTimer)
      reconcileTimer = null
    }
    clearAutoPolling()
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

  const currentRunId = (): string | null =>
    get().run?.id ?? session().agentRunId

  /**
   * 审批单状态 → 对应工具卡（审批卡与工具卡计数同源：同一条审批单只对应一张工具卡，
   * 工具卡显示「等待审批 / 已批准 / 已拒绝 / 已过期」，面板计数直接取自 approvals）。
   */
  const patchToolCallApproval = (approval: AgentApproval) => {
    patchAssistant((message) => {
      const calls = message.toolCalls
      if (!calls || calls.length === 0) return message
      const next = calls.map((call) =>
        call.id === approval.toolCallId || call.approvalId === approval.id
          ? {
              ...call,
              approvalId: approval.id,
              approvalStatus: approval.status,
              risk: approval.proposal?.risk ?? call.risk,
              status:
                approval.status === AGENT_APPROVAL_STATUS.APPROVED
                  ? ('running' as const)
                  : approval.status === AGENT_APPROVAL_STATUS.PENDING
                    ? ('pending' as const)
                    : call.status,
            }
          : call
      )
      return { ...message, toolCalls: next }
    })
  }

  /** 审批单合并：服务端条目覆盖同 id 的本地条目，未在列表中的本地条目保留 */
  const mergeApprovals = (incoming: AgentApproval[]): AgentApproval[] => {
    const current = get().approvals
    const merged = incoming.map((item) => {
      const local = current.find((approval) => approval.id === item.id)
      if (!local) return item
      return {
        ...local,
        ...item,
        proposal: item.proposal ?? local.proposal,
        diff: item.diff ?? local.diff,
      }
    })
    const extra = current.filter(
      (approval) => !incoming.some((item) => item.id === approval.id)
    )
    return [...merged, ...extra]
  }

  /** 审批单落状态（事件 / 决策响应 / 列表同步共用），并回填工具卡与时间线 */
  const upsertApproval = (approval: AgentApproval) => {
    const current = get().approvals
    const exists = current.some((item) => item.id === approval.id)
    set({
      approvals: exists
        ? current.map((item) =>
            item.id === approval.id
              ? {
                  ...item,
                  ...approval,
                  proposal: approval.proposal ?? item.proposal,
                  diff: approval.diff ?? item.diff,
                }
              : item
          )
        : [...current, approval],
    })
    set((state) => ({
      timeline: applyApprovalToTimeline(state.timeline, approval),
    }))
    patchToolCallApproval(approval)
  }

  const hasPendingApprovals = (approvals: AgentApproval[]): boolean =>
    approvals.some((approval) => isPendingApprovalStatus(approval.status))

  /**
   * 刷新恢复的 Auto 气泡补丁（P2）：点「继续」后撤掉暂停占位文案 /
   * 「等待审批」徽标，终态时换成 Auto 终态口径。只动恢复时记下的那一条。
   */
  const patchRestoredAutoMessage = (
    updater: (message: ChatMessage) => ChatMessage
  ) => {
    const key = restoredAutoMessageKey
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
      autoTracking: false,
      resumingAuto: false,
    })
    active = false
    session().setAgentRunId(null)
    closeStream()
    // 刷新恢复后续跑的 run 没有事件流：气泡由本处收口到 Auto 终态（P2）
    if (restoredAutoMessageKey) {
      const restoredKey = restoredAutoMessageKey
      const terminalText =
        autoTerminalMessageText(autoTerminalKind(get().run)) ?? message ?? ''
      patchRestoredAutoMessage((restored) => {
        const existing = restored.versions[0]?.content
        return {
          ...restored,
          status: CHAT_MESSAGE_STATUS.COMPLETE,
          runStatus: status,
          isReasoningStreaming: false,
          completedAt: Date.now(),
          durationMs: restored.startedAt
            ? Date.now() - restored.startedAt
            : 0,
          // 代码审计 P2：已有正文保留（终态由 runStatus 徽标 + 面板终态块表达），
          // 只有空正文 / 暂停占位才换成 Auto 终态文案。
          versions: isAutoPausePlaceholderContent(existing)
            ? [
                {
                  id: restored.versions[0]?.id ?? `${restoredKey}-v1`,
                  content: terminalText,
                },
              ]
            : restored.versions,
        }
      })
      restoredAutoMessageKey = null
    }
  }

  /**
   * 刷新恢复后「继续」的跟随（P2）：本页没有事件流可续（游标未持久化），
   * 按 5s 间隔取 `GET /agent/runs/{id}` 直到终态或再次暂停 —— 终态时落 run 快照、
   * 收口气泡并让进度面板渲染终态，不再永久停在「正在收集步骤进度…」。
   * 取快照连续失败 / 超过上限则停止并提示刷新查看。
   */
  const trackAutoRunUntilTerminal = (runId: string, runToken: number) => {
    clearAutoPolling()
    set({ autoTracking: true })
    const startedAt = Date.now()
    let failures = 0
    const schedule = () => {
      clearAutoPolling()
      autoPollTimer = setTimeout(
        () => {
          void tick()
        },
        failures > 0
          ? AUTO_TERMINAL_POLL_INTERVAL_MS * failures
          : AUTO_TERMINAL_POLL_INTERVAL_MS
      )
    }
    const tick = async () => {
      autoPollTimer = null
      if (runToken !== token) return
      if (Date.now() - startedAt > AUTO_TERMINAL_POLL_MAX_MS) {
        set({ autoTracking: false, error: AGENT_AUTO_COPY.trackingTimeout })
        return
      }
      try {
        const latest = await getAgentRun(runId)
        if (runToken !== token) return
        failures = 0
        set({ run: latest, error: null })
        if (isTerminalRunStatus(latest.status)) {
          finishRun(latest.status, latest.error)
          void get().refreshApprovals({ runId, syncPhase: false })
          return
        }
        // P3-1：续跑后可能再次进入暂停点（连续失败阈值可在继续后再次触发）。
        // 这是「可继续」的暂停态而非执行中：恢复暂停面板与操作入口并停止轮询，
        // 否则面板会一直挂在「正在等待服务端结果…」，直到 30 分钟上限才提示刷新。
        if (latest.status === AGENT_RUN_STATUS.WAITING_APPROVAL) {
          set({ autoTracking: false, autoPause: { consecutiveFailures: 0 } })
          patchRestoredAutoMessage((restored) => ({
            ...restored,
            status: CHAT_MESSAGE_STATUS.COMPLETE,
            runStatus: undefined,
            isReasoningStreaming: false,
            // 只把占位正文换回暂停口径；已产出的正文保留
            versions: isAutoPausePlaceholderContent(
              restored.versions[0]?.content
            )
              ? [
                  {
                    id: restored.versions[0]?.id ?? `${restored.key}-v1`,
                    content: AGENT_AUTO_COPY.restoredPaused,
                  },
                ]
              : restored.versions,
          }))
          return
        }
        schedule()
      } catch {
        if (runToken !== token) return
        failures += 1
        if (failures >= AUTO_TERMINAL_POLL_MAX_FAILURES) {
          set({ autoTracking: false, error: AGENT_AUTO_COPY.trackingFailed })
          return
        }
        schedule()
      }
    }
    autoPollTimer = setTimeout(() => {
      void tick()
    }, AUTO_TERMINAL_POLL_FIRST_DELAY_MS)
  }

  const failRun = (message: string, code?: string) => {
    patchAssistant((current) => ({
      ...current,
      status: CHAT_MESSAGE_STATUS.ERROR,
      errorCode: code || 'AGENT_ERROR',
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
            risk: event.risk,
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
        // INT-2493 无可用供应商：即使 run_finished 先到（error 事件缺失），也落配置引导态
        const providerMissing = isProviderNotConfiguredError(event.error)
        // Auto run 的空正文兜底用 Auto 终态口径（超预算 / 熔断 / 失败不显示成通用重试）
        const currentAutoRun = get().run
        const autoTerminalText =
          isAutoRun(currentAutoRun)
            ? autoTerminalMessageText(
                autoTerminalKind({
                  ...currentAutoRun,
                  status: event.status,
                  error: event.error,
                })
              )
            : null
        patchAssistant((message) => {
          const terminal = toTerminalPatch(event.status, message.startedAt, now)
          const withGuidance: Partial<ChatMessage> = providerMissing
            ? {
                ...terminal,
                status: CHAT_MESSAGE_STATUS.ERROR,
                errorCode: AGENT_PROVIDER_NOT_CONFIGURED_CODE,
              }
            : terminal
          if (message.versions[0]?.content || assistantContent) {
            return { ...message, ...withGuidance }
          }
          return {
            ...message,
            ...withGuidance,
            versions: [
              {
                id: message.versions[0]?.id ?? `${message.key}-v1`,
                content:
                  autoTerminalText ??
                  (event.status === AGENT_RUN_STATUS.CANCELLED
                    ? AGENT_ERROR_COPY.cancelled
                    : event.error || AGENT_ERROR_COPY.runFailed),
              },
            ],
          }
        })
        assistantKey = null
        // 终态：暂停点不再可操作（进度保留，供收口面板展示最终水位与产物）
        resumeRequested = false
        set({ autoPause: null, resumingAuto: false })
        finishRun(event.status, event.error)
        // 终态后补 token / 预算消耗（run_finished 不带 token 统计；失败不影响展示）
        void refreshRunSnapshot(get().run?.id ?? event.runId)
        void get().refreshApprovals({ syncPhase: false })
        return
      }
      case AGENT_EVENT_TYPE.ERROR: {
        if (event.recoverable === true) {
          // 可恢复的上游中断（网关合成 error 帧，code=UPSTREAM_*）：不关流、不进 run 终态，
          // 只提示「重连中」，由 SSE 层按 Last-Event-ID 续传（游标仍取已确认水位）。
          if (get().phase !== AGENT_RUN_PHASE.CANCELLING) {
            setPhase(AGENT_RUN_PHASE.RECONNECTING)
          }
          return
        }
        // Auto 熔断：后端先落 error 事件再 run_finished，但 error 事件本身会关流，
        // 紧随其后的终态帧可能收不到。这里按同一个错误码直接落 FAILED，保证
        // 熔断在面板上是明确终态（不是「运行失败但还显示运行中」）。
        // 气泡同口径用 Auto 熔断文案收口，不复用通用「Agent 运行失败，请重试」（P3-5）。
        const currentRun = get().run
        if (
          event.errorCode === AGENT_AUTO_ERROR_CODE.CONSECUTIVE_TOOL_FAILURES &&
          isAutoRun(currentRun)
        ) {
          set({
            run: {
              ...currentRun,
              status: AGENT_RUN_STATUS.FAILED,
              error: AGENT_AUTO_ERROR_CODE.CONSECUTIVE_TOOL_FAILURES,
            },
            autoPause: null,
          })
          patchAssistant((message) => {
            const terminal = {
              ...message,
              status: CHAT_MESSAGE_STATUS.COMPLETE,
              runStatus: AGENT_RUN_STATUS.FAILED,
              isReasoningStreaming: false,
              completedAt: Date.now(),
              durationMs: message.startedAt
                ? Date.now() - message.startedAt
                : 0,
            }
            // 代码审计 P2：已流式产出的正文保留（熔断由 runStatus 徽标 + 面板终态块表达），
            // 只有正文为空时才用 Auto 熔断文案，避免通用「Agent 运行失败，请重试」（P3-5）。
            if (message.versions[0]?.content || assistantContent) {
              return terminal
            }
            return {
              ...terminal,
              versions: [
                {
                  id: message.versions[0]?.id ?? `${message.key}-v1`,
                  content:
                    autoTerminalMessageText('circuit_break') ??
                    AGENT_ERROR_COPY.runFailed,
                },
              ],
            }
          })
          assistantKey = null
          finishRun(
            AGENT_RUN_STATUS.FAILED,
            AGENT_AUTO_ERROR_CODE.CONSECUTIVE_TOOL_FAILURES
          )
          return
        }
        failRun(event.errorMessage || AGENT_ERROR_COPY.runFailed, event.errorCode)
        return
      }
      case AGENT_EVENT_TYPE.APPROVAL_REQUIRED: {
        // 写操作提案（§9.4）：卡片数据来自事件本身（approval_required 载荷已含
        // tool / risk / proposal / expires_at），重连 / 刷新再用列表接口对齐。
        // §9.4.1：每张单一条事件，拆单载荷带 batch_id / batch_index / batch_total
        // （object_ref 不在 SSE 里，靠下面的列表刷新补齐）。
        upsertApproval({
          id: event.approvalId,
          runId: event.runId,
          toolCallId: event.toolCallId,
          status: AGENT_APPROVAL_STATUS.PENDING,
          proposal:
            event.proposal ??
            (event.tool
              ? {
                  tool: event.tool,
                  risk: event.risk,
                }
              : undefined),
          expiresAt: event.expiresAt,
          batchId: event.batchId,
          batchIndex: event.batchIndex,
          batchTotal: event.batchTotal,
        })
        if (get().phase !== AGENT_RUN_PHASE.CANCELLING) {
          setPhase(AGENT_RUN_PHASE.WAITING_APPROVAL)
        }
        // approval_required 事件不带 diff（只有列表接口有）：立刻按列表补齐
        // 「变更预览 / 决策人」，卡片首屏就能看到提案将发起的请求。
        void get().refreshApprovals({
          runId: event.runId,
          syncPhase: false,
        })
        return
      }
      case AGENT_EVENT_TYPE.RUN_STARTED: {
        const current = get().run
        if (current) {
          set({
            run: {
              ...current,
              status: event.status,
              mode: event.mode ?? current.mode,
              model: event.model ?? current.model,
              budget: event.budget ?? current.budget,
            },
          })
        }
        // Auto 暂停规则随 run_started 下发：开跑前即可展示「何时会暂停」（§9.4）
        if (event.mode === AGENT_RUN_MODE.AUTO && event.pausePolicy) {
          set({ autoPausePolicy: event.pausePolicy })
        }
        return
      }
      case AGENT_EVENT_TYPE.AUTO_STEP: {
        // 进度只更新水位，不改生命周期阶段（阶段仍由 RUNNING / 暂停 / 取消驱动）
        set({ autoProgress: event.progress })
        return
      }
      case AGENT_EVENT_TYPE.RUN_PAUSED: {
        // Auto 暂停（§9.4）：run 转 WAITING_APPROVAL 等用户确认继续；
        // 暂停点自身带用量，进度面板据此展示停在哪一项
        const progress = get().autoProgress
        const currentRun = get().run
        // 在途气泡随暂停收口（P3-2）：不再滞留「正在回复...」；暂停不是审批等待，
        // 不挂「等待审批」徽标（P3-1），具体状态由进度面板的「Auto 已暂停」表达
        patchAssistant((message) => {
          if (
            message.status !== CHAT_MESSAGE_STATUS.LOADING &&
            message.status !== CHAT_MESSAGE_STATUS.STREAMING
          ) {
            return message
          }
          return {
            ...message,
            status: CHAT_MESSAGE_STATUS.COMPLETE,
            isReasoningStreaming: false,
            completedAt: Date.now(),
            durationMs: message.startedAt ? Date.now() - message.startedAt : 0,
            versions: [
              {
                id: message.versions[0]?.id ?? `${message.key}-v1`,
                content:
                  message.versions[0]?.content ||
                  AGENT_AUTO_COPY.phasePendingResume,
              },
            ],
          }
        })
        set({
          autoPause: event.pause,
          autoProgress:
            progress && event.pause.usage
              ? {
                  ...progress,
                  usage: event.pause.usage,
                  limits: event.pause.limits ?? progress.limits,
                  ratio: event.pause.ratio ?? progress.ratio,
                  consecutiveFailures: event.pause.consecutiveFailures,
                  pauseReason: event.pause.reason,
                }
              : progress,
          run: currentRun
            ? { ...currentRun, status: AGENT_RUN_STATUS.WAITING_APPROVAL }
            : currentRun,
        })
        if (get().phase !== AGENT_RUN_PHASE.CANCELLING) {
          setPhase(AGENT_RUN_PHASE.WAITING_APPROVAL)
        }
        return
      }
      case AGENT_EVENT_TYPE.RUN_RESUMED: {
        // 用户确认继续：暂停点解除，同一预算暂停点不再触发（硬预算仍生效）
        const currentRun = get().run
        set({
          autoPause: null,
          run: currentRun
            ? { ...currentRun, status: AGENT_RUN_STATUS.RUNNING }
            : currentRun,
        })
        resumeRequested = false
        if (get().phase !== AGENT_RUN_PHASE.CANCELLING) {
          setPhase(AGENT_RUN_PHASE.RUNNING)
        }
        return
      }
      default:
        // context_compacted：只进时间线，不改变消息正文
        return
    }
  }

  /** 全局 sequence 单调去重：重连回放不会重复渲染同一段文本 */
  const handleEvent = (event: AgentRunEvent) => {
    // 网关合成的上游中断帧 id 取「已下发水位」，恰好等于水位，必须放行，
    // 否则用户既看不到中断提示、也只剩静默重连（INT-2520 P2-2）。
    const isRecoverableInterrupt =
      event.type === AGENT_EVENT_TYPE.ERROR && event.recoverable === true
    if (event.sequence <= lastSequence && !isRecoverableInterrupt) return
    if (event.type === AGENT_EVENT_TYPE.MESSAGE_DELTA) {
      const applied = lastDeltaSequences.get(event.messageId) ?? -1
      if (event.sequence <= applied) return
      lastDeltaSequences.set(event.messageId, event.sequence)
    }
    if (event.sequence > lastSequence) {
      lastSequence = event.sequence
      lastEventId = String(event.sequence)
    }
    // 时间线与消息补丁同源：先入时间线（保留后端 sequence），再落状态 / 正文
    set((state) => ({
      timeline: appendTimelineEntry(state.timeline, event),
    }))
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
    /** 是否已经历过一次 OPEN（之后的 OPEN 都是断线重连，需要对齐审批状态） */
    let sawOpen = false
    streamClose = subscribeAgentRunEvents(runId, {
      lastEventId,
      signal: controller.signal,
      onStatus: (status) => {
        if (runToken !== token) return
        set({ streamStatus: status })
        if (status === AGENT_STREAM_STATUS.RECONNECTING) {
          setPhase(AGENT_RUN_PHASE.RECONNECTING)
          return
        }
        if (status !== AGENT_STREAM_STATUS.OPEN) return
        if (get().phase !== AGENT_RUN_PHASE.CANCELLING) {
          setPhase(
            hasPendingApprovals(get().approvals)
              ? AGENT_RUN_PHASE.WAITING_APPROVAL
              : AGENT_RUN_PHASE.RUNNING
          )
        }
        // 断线重连（§12.2）：审批等待中重连要恢复待审批卡 —— SSE 只回放游标之后
        // 的事件，等待期间新增 / 已决的提案用列表接口对齐，已决的不再可操作。
        if (sawOpen) {
          void get().refreshApprovals()
        }
        sawOpen = true
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
    approvalRefreshToken += 1
    runSnapshotToken += 1
    decidingApprovals.clear()
    resumeRequested = false
    restoredAutoMessageKey = null
    clearAutoPolling()
    set({
      error: null,
      streamStatus: null,
      phase: AGENT_RUN_PHASE.PREPARING,
      approvals: [],
      approvalsLoading: false,
      approvalsError: null,
      decidingApprovalIds: [],
      timeline: [],
      autoProgress: null,
      autoPause: null,
      autoPausePolicy: null,
      resumingAuto: false,
      autoTracking: false,
    })

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

      // 只有 Auto 才带 mode / budget（普通对话请求体保持 {message} 单口径）
      const runInput: AgentRunInput = { message: text }
      if (options?.mode === AGENT_RUN_MODE.AUTO) {
        runInput.mode = 'auto'
        if (options.budget) runInput.budget = options.budget
      }
      const run = await createAgentRun(sessionId, runInput, buildIdempotencyKey())
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

  /**
   * 终态后补 run 快照（token_in / token_out / budget）：run_finished 不带统计字段，
   * 时间线的「预算消耗」需要它们。best-effort：失败保留已有值，不影响终态展示。
   */
  const refreshRunSnapshot = async (runId: string | undefined) => {
    if (!runId) return
    const snapshotToken = runSnapshotToken
    try {
      const latest = await getAgentRun(runId)
      if (snapshotToken !== runSnapshotToken) return
      const current = get().run
      if (!current || current.id !== latest.id) return
      // 只补统计字段：run_finished 已给出权威终态，快照不得把 CANCELLED /
      // FAILED 覆盖回 RUNNING（取消后立刻取快照的竞态）
      set({
        run: {
          ...current,
          mode: latest.mode ?? current.mode,
          tokenIn: latest.tokenIn ?? current.tokenIn,
          tokenOut: latest.tokenOut ?? current.tokenOut,
          budget: latest.budget ?? current.budget,
          startedAt: latest.startedAt ?? current.startedAt,
          finishedAt: latest.finishedAt ?? current.finishedAt,
        },
      })
    } catch {
      // 快照补失败不改变 run 终态（页面已有终态徽标；预算消耗可缺省）
    }
  }

  const refreshApprovals = async (options?: {
    runId?: string
    syncPhase?: boolean
  }) => {
    const runId = options?.runId ?? currentRunId()
    if (!runId) return
    const requestToken = ++approvalRefreshToken
    set({ approvalsLoading: true, approvalsError: null })
    try {
      const items = await listAgentApprovals(runId)
      if (requestToken !== approvalRefreshToken) return
      const merged = mergeApprovals(items)
      set({ approvals: merged, approvalsLoading: false })
      for (const approval of merged) {
        patchToolCallApproval(approval)
      }
      set((state) => ({
        timeline: merged.reduce(
          (entries, approval) => applyApprovalToTimeline(entries, approval),
          state.timeline
        ),
      }))
      if (options?.syncPhase !== false) {
        const phase = get().phase
        // 只有本 store 正在跟随的 run 才改阶段（刷新后无事件流的恢复场景不动阶段）
        if (!isAgentRunActive(phase)) return
        if (phase === AGENT_RUN_PHASE.CANCELLING) return
        const run = get().run
        if (run && isTerminalRunStatus(run.status)) return
        setPhase(
          hasPendingApprovals(merged)
            ? AGENT_RUN_PHASE.WAITING_APPROVAL
            : AGENT_RUN_PHASE.RUNNING
        )
      }
    } catch (err) {
      if (requestToken !== approvalRefreshToken) return
      set({
        approvalsLoading: false,
        approvalsError: AGENT_APPROVAL_COPY.loadFailed,
      })
      void err
    }
  }

  const decideApproval = async (
    approvalId: string,
    decision: AgentApprovalDecision,
    confirm = false
  ): Promise<string | null> => {
    // 防重复（§12.2「审批按钮防重复」）：同一审批单的请求在途时直接忽略连点
    if (decidingApprovals.has(approvalId)) return null
    const approval = get().approvals.find((item) => item.id === approvalId)
    if (!approval) return AGENT_APPROVAL_COPY.notFound
    // 已决 / 已过期不再发请求（过期由服务端 409 兜底，这里先拦住重复点击）
    if (!isPendingApprovalStatus(approval.status)) return null

    decidingApprovals.add(approvalId)
    set({ decidingApprovalIds: [...decidingApprovals] })
    const runToken = token
    try {
      const result = await decideAgentApproval(approvalId, decision, confirm)
      if (runToken !== token) return null
      upsertApproval(result.approval)
      const current = get().run
      if (current) {
        set({ run: { ...current, status: result.runStatus } })
      }
      // 只有本 store 正在跟随该 run 时才改阶段（刷新后无事件流的恢复场景不动阶段）
      if (runToken === token && isAgentRunActive(get().phase)) {
        if (result.runStatus === AGENT_RUN_STATUS.WAITING_APPROVAL) {
          setPhase(AGENT_RUN_PHASE.WAITING_APPROVAL)
        } else if (result.runStatus === AGENT_RUN_STATUS.RUNNING) {
          setPhase(AGENT_RUN_PHASE.RUNNING)
        }
      }
      return null
    } catch (err) {
      if (runToken !== token) return null
      if (err instanceof ApiError) {
        if (err.httpStatus === 404) return AGENT_APPROVAL_COPY.notFound
        if (err.httpStatus === 409) {
          // 并发 / 过期 / run 已收口：以服务端列表为准刷新卡片，再给出统一文案
          await get().refreshApprovals()
          return AGENT_APPROVAL_COPY.conflict
        }
        if (
          err.httpStatus === 400 &&
          err.rawCode === AGENT_APPROVAL_ERROR_CODE.CONFIRMATION_REQUIRED
        ) {
          // DESTRUCTIVE 批准缺 confirm（INT-2467）：决策未落库，卡片弹二次确认，
          // 确认后带 confirm=true 重发。
          return AGENT_APPROVAL_COPY.confirmRequired
        }
        return toAgentErrorMessage(err)
      }
      return AGENT_APPROVAL_COPY.decisionFailed
    } finally {
      decidingApprovals.delete(approvalId)
      set({ decidingApprovalIds: [...decidingApprovals] })
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
      set({ run: snapshot })
      if (isTerminalRunStatus(snapshot.status)) {
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

  /**
   * Auto 暂停后「继续」（POST /agent/runs/{id}/resume，INT-2474 §9.4）。
   * - 同一暂停点只发一次请求（按钮防连点）；
   * - 409 分两种：仍有待审批提案（先刷新审批列表并把用户引向审批卡）/
   *   已不在暂停态（刷新 run 快照，暂停面板据此消失），文案取服务端 detail；
   * - 成功后落 run 快照并回到 RUNNING；随后的 run_resumed 事件解除暂停面板。
   */
  const resumeAuto = async (): Promise<string | null> => {
    const current = get().run
    if (!current || resumeRequested) return null
    resumeRequested = true
    set({ resumingAuto: true })
    const runToken = token
    try {
      const snapshot = await resumeAgentRun(current.id)
      if (runToken !== token) return null
      // 竞态：服务端「继续」可能立刻跑完（短任务），事件流先一步把 run 收口。
      // 这时不能拿 resume 返回的旧快照把终态覆盖回 RUNNING（页面会永远停在运行中）。
      const live = get().run
      if (
        live &&
        live.id === snapshot.id &&
        isTerminalRunStatus(live.status)
      ) {
        set({ autoPause: null })
        return null
      }
      set({ run: snapshot, autoPause: null })
      if (isTerminalRunStatus(snapshot.status)) {
        emitSyntheticFinished(snapshot, snapshot.status, snapshot.error)
        finishRun(snapshot.status, snapshot.error)
        return null
      }
      // 刷新恢复后的「继续」（P2）：本页没有事件流可续（游标未持久化），
      // 撤掉暂停占位文案 / 「等待审批」徽标，改按快照轮询服务端终态，
      // 否则面板会永久停在「正在收集步骤进度…」而服务端已跑完。
      if (!active) {
        patchRestoredAutoMessage((restored) => {
          const existing = restored.versions[0]?.content ?? ''
          // 只替换空正文 / 暂停占位文案；已生成的正文保留
          const isPausePlaceholder = isAutoPausePlaceholderContent(existing)
          return {
            ...restored,
            status: CHAT_MESSAGE_STATUS.COMPLETE,
            runStatus: undefined,
            isReasoningStreaming: false,
            versions: [
              {
                id: restored.versions[0]?.id ?? `${restored.key}-v1`,
                content: isPausePlaceholder
                  ? AGENT_AUTO_COPY.restoredResuming
                  : existing,
              },
            ],
          }
        })
        trackAutoRunUntilTerminal(snapshot.id, runToken)
        return null
      }
      // 事件流已收口（FINISHED / ERROR）时不再把阶段拉回 RUNNING
      if (isAgentRunActive(get().phase)) {
        setPhase(AGENT_RUN_PHASE.RUNNING)
      }
      return null
    } catch (err) {
      if (runToken !== token) return null
      if (err instanceof ApiError) {
        if (err.httpStatus === 409) {
          // 待审批提案 / 已不在暂停态：都用服务端列表与快照对齐，再给中文文案
          await get().refreshApprovals()
          if (runToken !== token) return null
          if (hasPendingApprovals(get().approvals)) {
            return AGENT_AUTO_COPY.resumeNeedsApproval
          }
          try {
            const latest = await getAgentRun(current.id)
            if (runToken !== token) return null
            set({ run: latest })
            if (isTerminalRunStatus(latest.status)) {
              emitSyntheticFinished(latest, latest.status, latest.error)
              finishRun(latest.status, latest.error)
            } else if (latest.status !== AGENT_RUN_STATUS.WAITING_APPROVAL) {
              // 已继续 / 正在执行：暂停面板撤掉，交给事件流继续推送
              set({ autoPause: null })
              setPhase(AGENT_RUN_PHASE.RUNNING)
            }
          } catch {
            // 快照刷新失败不影响提示：用户可再点一次
          }
          return err.userMessage || AGENT_AUTO_COPY.resumeNotPaused
        }
        return err.userMessage || AGENT_AUTO_COPY.resumeFailed
      }
      return AGENT_AUTO_COPY.resumeFailed
    } finally {
      if (runToken === token) {
        resumeRequested = false
        set({ resumingAuto: false })
      }
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
    approvalRefreshToken += 1
    runSnapshotToken += 1
    decidingApprovals.clear()
    resumeRequested = false
    restoredAutoMessageKey = null
    closeStream()
    assistantKey = null
    assistantContent = ''
    restoredSessionId = null
    set({
      run: null,
      error: null,
      streamStatus: null,
      approvals: [],
      approvalsLoading: false,
      approvalsError: null,
      decidingApprovalIds: [],
      timeline: [],
      autoProgress: null,
      autoPause: null,
      autoPausePolicy: null,
      resumingAuto: false,
      autoTracking: false,
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
   *
   * 例外（INT-2472 审计 P2-1）：服务端 run 仍停在 `WAITING_APPROVAL` 且已恢复出待审批卡时，
   * 这一轮按「等待审批」中性收口（不落错误态、不给「重试」），把用户动作引向审批卡；
   * 只有拿不到待审批卡时才按事件流中断收口。
   */
  const reconcileInterruptedMessage = (
    runs: AgentRun[],
    options?: { approvalWaiting?: boolean; pausedAuto?: boolean }
  ) => {
    const pending = [...session().messages]
      .reverse()
      .find(
        (message) =>
          message.from === 'assistant' &&
          message.status !== undefined &&
          IN_FLIGHT_MESSAGE_STATUSES.has(message.status)
      )
    if (!pending) return
    // 记下暂停气泡：点「继续」后只更新这一条（撤掉暂停占位文案，终态收口，P2）
    restoredAutoMessageKey = options?.pausedAuto === true ? pending.key : null
    // 服务端仍有未终态的 run 时它才是这条悬挂气泡对应的那一轮；否则取最近一条
    const latestRun =
      runs.find((run) => !isTerminalRunStatus(run.status)) ??
      runs[runs.length - 1]
    const patch = (message: ChatMessage): ChatMessage => {
      // Auto 暂停（刷新恢复）：不落「事件流中断」错误态，气泡中性收口并引导继续 / 结束。
      // 暂停不是「等待审批」（P3-1）：不挂「等待审批」徽标，暂停状态由进度面板表达。
      if (
        options?.pausedAuto === true &&
        latestRun?.status === AGENT_RUN_STATUS.WAITING_APPROVAL
      ) {
        return {
          ...message,
          status: CHAT_MESSAGE_STATUS.COMPLETE,
          runStatus: undefined,
          isReasoningStreaming: false,
          versions: message.versions[0]?.content
            ? message.versions
            : [
                {
                  id: message.versions[0]?.id ?? `${message.key}-v1`,
                  content: AGENT_AUTO_COPY.restoredPaused,
                },
              ],
        }
      }
      const waitingApproval =
        latestRun?.status === AGENT_RUN_STATUS.WAITING_APPROVAL &&
        options?.approvalWaiting === true
      if (waitingApproval) {
        return {
          ...message,
          status: CHAT_MESSAGE_STATUS.COMPLETE,
          runStatus: AGENT_RUN_STATUS.WAITING_APPROVAL,
          isReasoningStreaming: false,
          // 保留已生成的正文；占位气泡没有正文时用「等待审批」兜底
          versions: message.versions[0]?.content
            ? message.versions
            : [
                {
                  id: message.versions[0]?.id ?? `${message.key}-v1`,
                  content: AGENT_APPROVAL_COPY.waitingMessage,
                },
              ],
        }
      }
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
   * 刷新 / 换宿主恢复：服务端最新 run 仍在等审批时，用列表接口恢复待审批卡
   * （§12.2「重连恢复待审批」）。本页没有接事件流，因此不改生命周期阶段
   * （syncPhase=false）：决策按钮照常可用，决策后由服务端继续执行。
   *
   * 返回恢复后是否确有可决策的待审批卡（P2-1：有卡才把悬挂气泡按「等待审批」收口）。
   */
  const restorePendingApprovals = async (
    runs: AgentRun[]
  ): Promise<boolean> => {
    const waiting = [...runs]
      .reverse()
      .find((run) => run.status === AGENT_RUN_STATUS.WAITING_APPROVAL)
    if (!waiting) return false
    const current = get().run
    if (!current || current.id !== waiting.id) set({ run: waiting })
    await get().refreshApprovals({ runId: waiting.id, syncPhase: false })
    return get().approvals.some((approval) =>
      isPendingApprovalStatus(approval.status)
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
        // 先恢复待审批卡，再收口悬挂气泡：run 仍在等审批时气泡落「等待审批」中性态（P2-1）
        const approvalWaiting = await restorePendingApprovals(detail.runs)
        if (runToken !== token) return
        if (session().agentSessionId !== sessionId) return
        // Auto 暂停（无待审批提案的 WAITING_APPROVAL）：恢复暂停面板，让用户可继续 / 结束
        const pausedAutoRun = approvalWaiting
          ? undefined
          : [...detail.runs]
              .reverse()
              .find(
                (run) =>
                  run.status === AGENT_RUN_STATUS.WAITING_APPROVAL &&
                  isAutoRun(run)
              )
        restoredAutoMessageKey = null
        if (pausedAutoRun) {
          set({
            run: pausedAutoRun,
            // 刷新不重接事件流：进度与暂停原因不可回放，用占位事实驱动「继续 / 结束」
            autoPause: { consecutiveFailures: 0 },
          })
          // 暂停气泡可能已在前端收口（P3-2，status=complete），reconcile 只找「进行中」
          // 气泡会落空；这里兜底记本轮（最后一条 user 消息之后）的 assistant 气泡。
          // 代码审计 P2：不能无脑取最后一条 assistant —— 刷新前消息未落盘 / 本 run 没有
          // 服务端气泡时，那可能是上一轮正常对话的回答，继续后会被静默覆盖。
          const messages = session().messages
          let lastUserIndex = -1
          for (let index = messages.length - 1; index >= 0; index -= 1) {
            if (messages[index].from === 'user') {
              lastUserIndex = index
              break
            }
          }
          const turnAssistant = [...messages.slice(lastUserIndex + 1)]
            .reverse()
            .find((message) => message.from === 'assistant')
          restoredAutoMessageKey = turnAssistant?.key ?? null
        }
        reconcileInterruptedMessage(detail.runs, {
          approvalWaiting,
          pausedAuto: Boolean(pausedAutoRun),
        })
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
    approvals: [],
    approvalsLoading: false,
    approvalsError: null,
    decidingApprovalIds: [],
    timeline: [],
    autoProgress: null,
    autoPause: null,
    autoPausePolicy: null,
    resumingAuto: false,
    autoTracking: false,
    send,
    cancel,
    resumeAuto,
    decideApproval,
    refreshApprovals,
    reset,
    restore,
    attachHost,
    detachHost,
  }
})
