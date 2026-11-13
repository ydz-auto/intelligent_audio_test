/**
 * Agent 会话 / Run / 事件流 API（infrastructure 层；契约见
 * doc/agent化/07_单Agent_Skills落地方案.md §11 API 与 SSE）。
 *
 * 端点（§11 冻结）：
 *   POST /agent/sessions                       创建会话
 *   GET  /agent/sessions/{id}                  会话与最近消息
 *   POST /agent/sessions/{id}/runs             发起 run（Idempotency-Key 头，§9.2）
 *   GET  /agent/runs/{id}                      run 快照
 *   GET  /agent/runs/{id}/events?cursor=       SSE（Last-Event-ID 续传，§11/§9.2）
 *   POST /agent/runs/{id}/cancel               取消
 *   GET  /agent/runs/{id}/approvals            待审批提案（M2 审批卡，本卡接空列表）
 *
 * 传输：普通请求走 client.ts 统一封装（JWT / 错误码归一）；事件流必须 fetch +
 * ReadableStream（EventSource 不能带 Authorization 头），鉴权与 /sse/events 同口径。
 * 架构红线：本文件只产出 camelCase 领域对象，snake_case 转换在
 * infrastructure/dto/agent.dto.ts。
 */
import {
  AGENT_DISABLED_CODE,
  AGENT_ERROR_COPY,
  AGENT_EVENT_TYPE,
  type AgentApproval,
  type AgentRun,
  type AgentRunEvent,
  type AgentRunInput,
  type AgentSession,
  type AgentSessionDetail,
} from '@/domain/models/agent'
import {
  toAgentApprovals,
  toAgentRun,
  toAgentRunCreateDto,
  toAgentRunEvent,
  toAgentRunFromCreateResponse,
  toAgentSession,
  toAgentSessionCreateDto,
  toAgentSessionDetail,
  type AgentApprovalsResponseDto,
  type AgentEventDto,
  type AgentRunCreateResponseDto,
  type AgentRunDto,
  type AgentSessionDetailDto,
  type AgentSessionDto,
} from '@/infrastructure/dto/agent.dto'
import { parseSseFrame } from '@/infrastructure/realtime/sse'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

import { ApiError } from './api-error'
import { API_BASE_URL, request, tryRefreshToken, type ApiRequestOptions } from './client'

/** 契约路径（§11；相对 API_BASE_URL=/api/v1） */
export const AGENT_API_PATHS = {
  sessions: '/agent/sessions',
  session: (sessionId: string) => `/agent/sessions/${encodeURIComponent(sessionId)}`,
  sessionRuns: (sessionId: string) =>
    `/agent/sessions/${encodeURIComponent(sessionId)}/runs`,
  run: (runId: string) => `/agent/runs/${encodeURIComponent(runId)}`,
  runEvents: (runId: string) => `/agent/runs/${encodeURIComponent(runId)}/events`,
  runCancel: (runId: string) => `/agent/runs/${encodeURIComponent(runId)}/cancel`,
  runApprovals: (runId: string) =>
    `/agent/runs/${encodeURIComponent(runId)}/approvals`,
} as const

// ===== 事件流参数（禁止魔法数字；§5.3「预算、阈值、超时写入配置」） =====

/** 断线重连退避初值（ms） */
const STREAM_RECONNECT_BASE_MS = 1_000
/** 断线重连退避上限（ms） */
const STREAM_RECONNECT_MAX_MS = 15_000
/** 单次订阅最多重连次数（耗尽后 onFailure，不无限重连） */
const STREAM_MAX_RECONNECT_ATTEMPTS = 8
/** 心跳超时（ms）：超过即判死重连（与 /sse/events 同值） */
const STREAM_HEARTBEAT_TIMEOUT_MS = 30_000

/** 事件流连接状态（页面按 reconnecting 显示重连提示） */
export const AGENT_STREAM_STATUS = {
  CONNECTING: 'connecting',
  OPEN: 'open',
  RECONNECTING: 'reconnecting',
  CLOSED: 'closed',
  FAILED: 'failed',
} as const

export type AgentStreamStatus =
  (typeof AGENT_STREAM_STATUS)[keyof typeof AGENT_STREAM_STATUS]

export interface SubscribeAgentRunEventsOptions {
  /** 续传游标（Last-Event-ID；上一次收到的最后事件 id） */
  lastEventId?: string | null
  onEvent: (event: AgentRunEvent) => void
  onStatus?: (status: AgentStreamStatus) => void
  /** 不可恢复失败（鉴权 / 未部署 / 重连耗尽）→ 中文文案，页面落错误态 */
  onFailure?: (message: string) => void
  signal?: AbortSignal
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * 503 是否真的是「Agent 总开关关闭」：网关 agent_guard 抛
 * HTTPException(detail={code: AGENT_DISABLED, message})，FastAPI 落成
 * `{"detail": {"code": "AGENT_DISABLED", ...}}`。其余 503（网关转发不到
 * agent_service、credential store 不可用等）是服务不可达，不能报成未开启。
 */
function isAgentDisabledPayload(payload: unknown): boolean {
  if (!isObject(payload)) return false
  if (payload.code === AGENT_DISABLED_CODE) return true
  return isObject(payload.detail) && payload.detail.code === AGENT_DISABLED_CODE
}

/** HTTP 状态 + 响应体 → Agent 通道中文错误文案 */
export function toAgentErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isNetworkError) return AGENT_ERROR_COPY.network
    if (error.httpStatus === 401 || error.httpStatus === 403) {
      return AGENT_ERROR_COPY.unauthorized
    }
    if (error.httpStatus === 404) return AGENT_ERROR_COPY.notFound
    if (error.httpStatus === 503) {
      return isAgentDisabledPayload({ detail: error.detail })
        ? AGENT_ERROR_COPY.disabled
        : AGENT_ERROR_COPY.serviceUnavailable
    }
    return error.userMessage || AGENT_ERROR_COPY.runFailed
  }
  if (error instanceof Error && error.message) return error.message
  return AGENT_ERROR_COPY.runFailed
}

/** 事件流错误响应体（空体 / 非 JSON 返回 null，仅用于 503 来源判定） */
async function readStreamErrorPayload(response: Response): Promise<unknown> {
  try {
    const text = await response.text()
    return text.trim() ? (JSON.parse(text) as unknown) : null
  } catch {
    return null
  }
}

/** SSE 帧 data：object 直接用；string 尝试 JSON 解析（后端可能不写 event: 行） */
function toFramePayload(data: unknown): unknown {
  if (typeof data !== 'string') return data
  const text = data.trim()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

/** 不可重连的 HTTP 状态（未部署 / 未开启 / 鉴权失败；继续重连只会空转） */
function isFatalStreamStatus(status: number): boolean {
  return status === 401 || status === 403 || status === 404 || status === 410 || status === 503
}

function streamFailureMessage(status: number, payload: unknown): string {
  if (status === 401 || status === 403) return AGENT_ERROR_COPY.unauthorized
  if (status === 404 || status === 410) return AGENT_ERROR_COPY.notFound
  if (status === 503) {
    return isAgentDisabledPayload(payload)
      ? AGENT_ERROR_COPY.disabled
      : AGENT_ERROR_COPY.serviceUnavailable
  }
  return AGENT_ERROR_COPY.streamFailed
}

// ===== 会话 / Run 普通请求 =====

/** POST /agent/sessions —— 首次发送前建会话（title 缺省由后端按首条消息生成） */
export async function createAgentSession(
  input: { title?: string } = {},
  options?: ApiRequestOptions
): Promise<AgentSession> {
  const dto = await request<AgentSessionDto>(
    'POST',
    AGENT_API_PATHS.sessions,
    toAgentSessionCreateDto(input.title),
    options
  )
  return toAgentSession(dto)
}

/**
 * GET /agent/sessions/{id} —— 会话与最近消息。
 * 真实响应是 `{session, messages, runs}` 信封（网关透明转发），解信封在此层做。
 */
export async function getAgentSession(
  sessionId: string,
  options?: ApiRequestOptions
): Promise<AgentSessionDetail> {
  const dto = await request<AgentSessionDetailDto>(
    'GET',
    AGENT_API_PATHS.session(sessionId),
    undefined,
    options
  )
  return toAgentSessionDetail(dto)
}

/**
 * POST /agent/sessions/{id}/runs —— 发起 run。
 * 幂等键走 Idempotency-Key 头（§9.2：run_id + step_id + tool + args_hash 由后端落；
 * 前端只保证「同一轮发送只发一次」且重试复用同一键）。
 * 真实响应是 `{run, created}` 信封：created=true 为 201 新建、false 为 200 幂等回放；
 * 两种都返回同一个 run，解信封不泄漏到 application 层。
 */
export async function createAgentRun(
  sessionId: string,
  input: AgentRunInput,
  idempotencyKey: string,
  options?: ApiRequestOptions
): Promise<AgentRun> {
  const controllerHeaders: Record<string, string> = {
    ...((options?.headers as Record<string, string> | undefined) ?? {}),
    'Idempotency-Key': idempotencyKey,
  }
  const dto = await request<AgentRunCreateResponseDto>(
    'POST',
    AGENT_API_PATHS.sessionRuns(sessionId),
    toAgentRunCreateDto(input),
    { ...options, headers: controllerHeaders }
  )
  return toAgentRunFromCreateResponse(dto)
}

/** GET /agent/runs/{id} —— run 快照（重连时核对终态） */
export async function getAgentRun(
  runId: string,
  options?: ApiRequestOptions
): Promise<AgentRun> {
  const dto = await request<AgentRunDto>(
    'GET',
    AGENT_API_PATHS.run(runId),
    undefined,
    options
  )
  return toAgentRun(dto)
}

/** POST /agent/runs/{id}/cancel —— 取消（后端恒返 RunResponse 快照，按 JSON 解析） */
export async function cancelAgentRun(
  runId: string,
  options?: ApiRequestOptions
): Promise<AgentRun> {
  const dto = await request<AgentRunDto>(
    'POST',
    AGENT_API_PATHS.runCancel(runId),
    undefined,
    options
  )
  return toAgentRun(dto)
}

/**
 * GET /agent/runs/{id}/approvals —— 待审批提案（`{"items": [...]}`）。
 * 审批卡与决策流程属 M2（INT-2472）；本卡只接列表契约。端点已实现，404 只可能是
 * 路径/网关配错，照常上抛（不伪装成「暂无待审批」）。
 */
export async function listAgentApprovals(
  runId: string,
  options?: ApiRequestOptions
): Promise<AgentApproval[]> {
  const dto = await request<AgentApprovalsResponseDto>(
    'GET',
    AGENT_API_PATHS.runApprovals(runId),
    undefined,
    options
  )
  return toAgentApprovals(dto)
}

// ===== Run 事件流（SSE + Last-Event-ID 续传） =====

function buildEventsUrl(runId: string, cursor: string | null): string {
  const path = `${API_BASE_URL}${AGENT_API_PATHS.runEvents(runId)}`
  return cursor ? `${path}?cursor=${encodeURIComponent(cursor)}` : path
}

/**
 * 订阅 GET /agent/runs/{id}/events。
 * - 断线 / 心跳超时自动重连（指数退避），每次重连带 Last-Event-ID（最近事件 id）
 *   与 ?cursor=，服务端从游标续发，不丢消息；
 * - 收到 run_finished 终止（不再重连）；鉴权失败 / 未部署 / 503 直接失败不重连；
 * - 返回解绑函数（调用后断开连接并停止重连）。
 * 事件去重（sequence / message_id）在 application/agent/use-agent-run 内做。
 */
export function subscribeAgentRunEvents(
  runId: string,
  options: SubscribeAgentRunEventsOptions
): () => void {
  const { onEvent, onStatus, onFailure, signal } = options

  let stopped = false
  let terminal = false
  let attempt = 0
  /** 本轮连接是否已因 401 刷过 token（只刷一次，防死循环） */
  let refreshTried = false
  let cursor: string | null = options.lastEventId ?? null
  let controller: AbortController | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let lastFrameAt = Date.now()
  let signalAbortListener: (() => void) | null = null

  function setStatus(status: AgentStreamStatus): void {
    if (!stopped) onStatus?.(status)
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
      if (Date.now() - lastFrameAt > STREAM_HEARTBEAT_TIMEOUT_MS) {
        // 心跳超时判死，强制断开触发重连
        controller?.abort()
      }
    }, STREAM_HEARTBEAT_TIMEOUT_MS / 2)
  }

  function teardown(): void {
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

  function fail(message: string): void {
    terminal = true
    setStatus(AGENT_STREAM_STATUS.FAILED)
    onFailure?.(message)
    teardown()
  }

  function scheduleReconnect(): void {
    if (stopped || terminal) return
    attempt += 1
    if (attempt > STREAM_MAX_RECONNECT_ATTEMPTS) {
      fail(AGENT_ERROR_COPY.streamFailed)
      return
    }
    const delay = Math.min(
      STREAM_RECONNECT_BASE_MS * 2 ** (attempt - 1),
      STREAM_RECONNECT_MAX_MS
    )
    setStatus(AGENT_STREAM_STATUS.RECONNECTING)
    reconnectTimer = setTimeout(() => {
      void connect()
    }, delay)
  }

  function handleFrame(raw: string): void {
    lastFrameAt = Date.now()
    const frame = parseSseFrame(raw)
    if (!frame) return
    const payload = toFramePayload(frame.data)
    if (!isObject(payload)) return

    // 真实帧：event: <type> + data 为平铺 JSON（事件字段与 run_id/sequence/type/
    // timestamp 同级）；事件类型优先取帧 event 名，缺省回退载荷 type 字段。
    const frameType =
      frame.eventType !== 'message' && frame.eventType !== '' ? frame.eventType : undefined
    const dto: AgentEventDto = {
      ...(payload as AgentEventDto),
      ...(frameType ? { type: frameType } : {}),
    }
    const event = toAgentRunEvent(dto)
    if (!event) return

    const nextCursor = frame.id ?? String(event.sequence)
    cursor = nextCursor
    if (event.type === AGENT_EVENT_TYPE.RUN_FINISHED) {
      onEvent(event)
      terminal = true
      teardown()
      return
    }
    onEvent(event)
  }

  async function connect(): Promise<void> {
    if (stopped || terminal) return
    controller = new AbortController()

    if (signal) {
      if (signalAbortListener) {
        signal.removeEventListener('abort', signalAbortListener)
        signalAbortListener = null
      }
      if (signal.aborted) {
        teardown()
        return
      }
      const onAbort = (): void => teardown()
      signalAbortListener = onAbort
      signal.addEventListener('abort', onAbort, { once: true })
    }

    setStatus(
      attempt === 0 ? AGENT_STREAM_STATUS.CONNECTING : AGENT_STREAM_STATUS.RECONNECTING
    )
    const token = authTokenStore.get()
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    }
    if (token) headers.Authorization = `Bearer ${token}`
    // §9.2/§11 断线续传：从最近事件 id 续发，不重复渲染已收事件
    if (cursor) headers['Last-Event-ID'] = cursor

    let response: Response
    try {
      response = await fetch(buildEventsUrl(runId, cursor), {
        headers,
        signal: controller.signal,
      })
    } catch {
      scheduleReconnect()
      return
    }
    if (!response.ok) {
      // 401：与 client.ts 同口径（refresh 一次后重放）。JWT 24h，长 run 续传
      // 时可能已过期，直接判「无权使用」会把登录态临近过期误报成权限问题。
      if (response.status === 401 && !refreshTried) {
        refreshTried = true
        if (await tryRefreshToken()) {
          if (!stopped && !terminal) void connect()
          return
        }
      }
      // 503 要区分「总开关关闭」与「服务不可达」，需读响应体里的 code
      const errorPayload = isFatalStreamStatus(response.status)
        ? await readStreamErrorPayload(response)
        : null
      if (isFatalStreamStatus(response.status)) {
        fail(streamFailureMessage(response.status, errorPayload))
        return
      }
      scheduleReconnect()
      return
    }
    if (!response.body) {
      scheduleReconnect()
      return
    }

    lastFrameAt = Date.now()
    startHeartbeat()
    setStatus(AGENT_STREAM_STATUS.OPEN)
    attempt = 0
    refreshTried = false

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      for (;;) {
        if (terminal) break
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
      if (!stopped && !terminal) scheduleReconnect()
    } catch {
      if (!stopped && !terminal) scheduleReconnect()
    } finally {
      stopHeartbeat()
    }
  }

  void connect()
  return teardown
}
