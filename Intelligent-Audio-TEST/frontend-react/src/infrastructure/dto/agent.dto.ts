/**
 * Agent DTO 与转换（infrastructure/dto 层——后端 snake_case 契约唯一出现层）。
 * 契约来源：doc/agent化/07_单Agent_Skills落地方案.md §10 数据模型 + §11 API 与 SSE；
 * 路径/方法按 §11 冻结，请求体与事件 payload 的字段按 §5/§9 语义命名，待 INT-2451
 * 后端落地后按实际 schema 微调（本层是唯一改动点）。
 *
 * 架构红线：前端（domain / application / interfaces）只见 camelCase；
 * snake_case ↔ camelCase 只在此文件发生。
 */
import {
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_RESULT_STATUS,
  isRecoverableAgentErrorCode,
  normalizeRunStatus,
  normalizeToolRisk,
  type AgentApproval,
  type AgentEventSourceRef,
  type AgentRun,
  type AgentRunEvent,
  type AgentRunInput,
  type AgentSession,
  type AgentSessionDetail,
} from '@/domain/models/agent'

/** POST /agent/sessions 请求体（title 缺省由后端按首条消息生成） */
export interface AgentSessionCreateDto {
  title?: string
}

/** POST /agent/sessions 响应 / GET /agent/sessions/{id}（agent_session 表字段） */
export interface AgentSessionDto {
  id: string
  title?: string
  active_skill?: string
  model?: string
  created_at?: string
  updated_at?: string
}

/** POST /agent/sessions/{id}/runs 请求体（§5.1 输入 user_message；幂等键走 Idempotency-Key 头） */
export interface AgentRunCreateDto {
  message: string
}

/**
 * POST /agent/sessions/{id}/runs 响应（后端 CreateRunResponse：`{run, created}`，
 * 网关 agent_runtime_bp._to_response 原样透传，不拆信封）。
 * created=true=201 新建；created=false=200 幂等回放（同一 Idempotency-Key 已存在）。
 */
export interface AgentRunCreateResponseDto {
  run: AgentRunDto
  created?: boolean
}

/** GET /agent/sessions/{id} 响应（后端 SessionDetailResponse：`{session, messages, runs}`） */
export interface AgentSessionDetailDto {
  session: AgentSessionDto
  messages?: AgentSessionMessageDto[]
  runs?: AgentRunDto[]
}

/** 会话历史消息（context_assembler.recent_session_messages 原样字段） */
export interface AgentSessionMessageDto {
  role?: string
  content?: string
  tool_call_id?: string
}

/** GET /agent/runs/{id}/approvals 响应（后端 `{"items": [...]}`；M0 恒为空列表） */
export interface AgentApprovalsResponseDto {
  items?: AgentApprovalDto[]
}

/** GET /agent/runs/{id} / POST /agent/runs/{id}/cancel 响应（agent_run 表字段，扁平） */
export interface AgentRunDto {
  id: string
  session_id?: string
  status?: string
  model?: string
  token_in?: number
  token_out?: number
  created_at?: string
  started_at?: string
  finished_at?: string
  error?: string
}

/** GET /agent/runs/{id}/approvals 列表项（agent_approval 表字段；M2 审批卡用） */
export interface AgentApprovalDto {
  id: string
  run_id?: string
  tool_call_id?: string
  status?: string
  proposal?: unknown
  diff?: unknown
  expires_at?: string
}

/** sourceRefs 原始形态（报告七表：报告 ID + 指标 ID + 数据版本） */
export interface AgentSourceRefDto {
  report_id: number
  metric_id?: string
  data_version?: string
  verified?: boolean
}

/**
 * 单条 SSE 事件原始帧。
 * 真实形态（agent_service/routes.py::_sse_frame）：`event.payload` 的键与
 * run_id / sequence / type / timestamp **平铺在同一层**，没有嵌套 payload。
 * `payload` 字段仅兼容早期草案形态，转换时两层合并（顶层优先）。
 */
export interface AgentEventDto {
  run_id?: string
  sequence?: number
  type?: string
  timestamp?: string
  payload?: Record<string, unknown>
  [key: string]: unknown
}

/** 从事件顶层或 payload 里取字段（后端两种落法都兼容；snake 键只在本层出现） */
function pick(
  payload: Record<string, unknown>,
  ...keys: string[]
): unknown {
  for (const key of keys) {
    const value = payload[key]
    if (value !== undefined && value !== null) return value
  }
  return undefined
}

function toStringValue(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function toFiniteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/** snake_case sourceRefs → camelCase 域对象（非数组/字段缺失返回 undefined） */
export function toAgentSourceRefs(value: unknown): AgentEventSourceRef[] | undefined {
  if (!Array.isArray(value)) return undefined
  const refs: AgentEventSourceRef[] = []
  for (const item of value) {
    if (typeof item !== 'object' || item === null) continue
    const raw = item as Record<string, unknown>
    const reportId = toFiniteNumber(pick(raw, 'report_id', 'reportId'))
    if (reportId === undefined) continue
    refs.push({
      reportId,
      metricId: toStringValue(pick(raw, 'metric_id', 'metricId')),
      dataVersion: toStringValue(pick(raw, 'data_version', 'dataVersion')),
      verified:
        typeof pick(raw, 'verified') === 'boolean'
          ? (pick(raw, 'verified') as boolean)
          : undefined,
    })
  }
  return refs.length > 0 ? refs : undefined
}

export function toAgentSession(dto: AgentSessionDto): AgentSession {
  return {
    id: dto.id,
    title: dto.title ?? '',
    activeSkill: dto.active_skill,
    model: dto.model,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export function toAgentRun(dto: AgentRunDto): AgentRun {
  return {
    id: dto.id,
    sessionId: dto.session_id ?? '',
    status: normalizeRunStatus(dto.status),
    model: dto.model,
    tokenIn: toFiniteNumber(dto.token_in),
    tokenOut: toFiniteNumber(dto.token_out),
    startedAt: dto.started_at,
    finishedAt: dto.finished_at,
    error: dto.error,
  }
}

/**
 * POST /agent/sessions/{id}/runs 响应解信封：真实后端为 `{run, created}`，
 * 网关透明转发不拆；解信封只在 infrastructure 做（application 拿不到 run.id 会
 * 用 undefined 订阅事件流，服务端 run 继续跑成孤儿）。
 * 兼容扁平 run 形态（早期草案/单测桩）。
 */
export function toAgentRunFromCreateResponse(
  dto: AgentRunCreateResponseDto | AgentRunDto
): AgentRun {
  const envelope = dto as AgentRunCreateResponseDto
  const run = isObject(envelope.run) ? envelope.run : (dto as AgentRunDto)
  return toAgentRun(run)
}

/** GET /agent/sessions/{id} 响应（`{session, messages, runs}` 信封，网关不拆） */
export function toAgentSessionDetail(
  dto: AgentSessionDetailDto
): AgentSessionDetail {
  return {
    session: toAgentSession(dto.session),
    messages: (dto.messages ?? []).map((message) => ({
      role: toStringValue(message.role) ?? 'assistant',
      content: toStringValue(message.content) ?? '',
      toolCallId: toStringValue(message.tool_call_id),
    })),
    runs: (dto.runs ?? []).map(toAgentRun),
  }
}

/** GET /agent/runs/{id}/approvals 响应（真实 `{"items": [...]}`；兼容直接数组） */
export function toAgentApprovals(
  dto: AgentApprovalDto[] | AgentApprovalsResponseDto
): AgentApproval[] {
  const items = Array.isArray(dto) ? dto : (dto.items ?? [])
  return items.map(toAgentApproval)
}

export function toAgentApproval(dto: AgentApprovalDto): AgentApproval {
  const status =
    dto.status === 'APPROVED' ||
    dto.status === 'REJECTED' ||
    dto.status === 'EXPIRED'
      ? dto.status
      : 'PENDING'
  return {
    id: dto.id,
    runId: dto.run_id ?? '',
    toolCallId: dto.tool_call_id,
    status,
    proposal: dto.proposal,
    diff: dto.diff,
    expiresAt: dto.expires_at,
  }
}

export function toAgentSessionCreateDto(title?: string): AgentSessionCreateDto {
  return title ? { title } : {}
}

export function toAgentRunCreateDto(input: AgentRunInput): AgentRunCreateDto {
  return { message: input.message }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** tool_call 只有 arguments（后端不下发 summary）：前端做只读展示压缩，不解读语义 */
const TOOL_ARGUMENTS_SUMMARY_MAX_CHARS = 120
/** tool_result 的 content 可能很长：工具卡摘要截断 */
const TOOL_RESULT_SUMMARY_MAX_CHARS = 200

function clampText(
  value: string | undefined,
  maxChars: number
): string | undefined {
  if (!value) return undefined
  return value.length > maxChars ? `${value.slice(0, maxChars)}…` : value
}

/** tool_call 摘要：真实字段是 arguments（后端无 summary / args_summary） */
function summarizeToolArguments(value: unknown): string | undefined {
  if (!isObject(value)) return undefined
  try {
    const text = JSON.stringify(value)
    if (!text || text === '{}') return undefined
    return clampText(text, TOOL_ARGUMENTS_SUMMARY_MAX_CHARS)
  } catch {
    return undefined
  }
}

/**
 * 事件载荷合并：真实后端把事件字段（message_id / delta / status / ok ...）
 * 平铺在 SSE data 顶层（routes.py::_sse_frame），早期草案则嵌在 `payload`；
 * 两层合并、顶层优先，两种形态都能解析。
 */
function toEventPayload(dto: AgentEventDto): Record<string, unknown> {
  const nested = isObject(dto.payload) ? dto.payload : {}
  return { ...nested, ...dto }
}

/**
 * SSE 原始事件 → camelCase 领域事件。
 * 未识别的事件类型返回 null（忽略未知事件，不把未知载荷当已知结构渲染）。
 * 字段读取口径见 toEventPayload（平铺优先，兼容嵌套）。
 */
export function toAgentRunEvent(dto: AgentEventDto): AgentRunEvent | null {
  const payload = toEventPayload(dto)
  const type = toStringValue(pick(payload, 'type'))
  const sequence = toFiniteNumber(pick(payload, 'sequence'))
  if (!type || sequence === undefined) return null

  const base = {
    runId: toStringValue(pick(payload, 'run_id')) ?? '',
    sequence,
    timestamp: toStringValue(pick(payload, 'timestamp')) ?? '',
  }

  switch (type) {
    case AGENT_EVENT_TYPE.RUN_STARTED:
      // 后端 run_started 载荷为 {user_message, session_id, model, budget}，无 status；
      // 收到即代表 run 已受理进入执行，状态归一为 RUNNING。
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_STARTED,
        status: normalizeRunStatus(pick(payload, 'status')),
        model: toStringValue(pick(payload, 'model')),
      }
    case AGENT_EVENT_TYPE.MESSAGE_DELTA: {
      const messageId = toStringValue(pick(payload, 'message_id', 'messageId'))
      if (!messageId) return null
      return {
        ...base,
        type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
        messageId,
        delta: toStringValue(pick(payload, 'delta', 'content')) ?? '',
      }
    }
    case AGENT_EVENT_TYPE.TOOL_CALL: {
      const toolCallId = toStringValue(pick(payload, 'tool_call_id', 'toolCallId'))
      const tool = toStringValue(pick(payload, 'tool', 'name'))
      if (!toolCallId || !tool) return null
      return {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_CALL,
        toolCallId,
        tool,
        risk: normalizeToolRisk(pick(payload, 'risk')),
        summary:
          toStringValue(pick(payload, 'summary', 'args_summary')) ??
          summarizeToolArguments(pick(payload, 'arguments')),
      }
    }
    case AGENT_EVENT_TYPE.TOOL_RESULT: {
      const toolCallId = toStringValue(pick(payload, 'tool_call_id', 'toolCallId'))
      if (!toolCallId) return null
      const rawStatus = toStringValue(pick(payload, 'status'))
      const ok = pick(payload, 'ok')
      // 真实载荷为 {ok, content, error_code}，没有 status；ok=false → FAILED。
      const status =
        rawStatus === AGENT_TOOL_RESULT_STATUS.FAILED ||
        rawStatus === AGENT_TOOL_RESULT_STATUS.CANCELLED
          ? rawStatus
          : typeof ok === 'boolean' && !ok
            ? AGENT_TOOL_RESULT_STATUS.FAILED
            : AGENT_TOOL_RESULT_STATUS.SUCCEEDED
      const errorCode = toStringValue(pick(payload, 'error_code', 'errorCode'))
      return {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_RESULT,
        toolCallId,
        status,
        summary:
          toStringValue(pick(payload, 'summary', 'result_summary')) ??
          clampText(
            toStringValue(pick(payload, 'content')) ?? errorCode,
            TOOL_RESULT_SUMMARY_MAX_CHARS
          ),
        errorCode,
        sourceRefs: toAgentSourceRefs(pick(payload, 'source_refs', 'sourceRefs')),
      }
    }
    case AGENT_EVENT_TYPE.APPROVAL_REQUIRED: {
      const approvalId = toStringValue(pick(payload, 'approval_id', 'approvalId'))
      if (!approvalId) return null
      return {
        ...base,
        type: AGENT_EVENT_TYPE.APPROVAL_REQUIRED,
        approvalId,
        toolCallId: toStringValue(pick(payload, 'tool_call_id', 'toolCallId')),
        proposal: pick(payload, 'proposal'),
      }
    }
    case AGENT_EVENT_TYPE.CONTEXT_COMPACTED:
      return {
        ...base,
        type: AGENT_EVENT_TYPE.CONTEXT_COMPACTED,
        level: toStringValue(pick(payload, 'level')),
      }
    case AGENT_EVENT_TYPE.RUN_FINISHED: {
      // 真实载荷 {status, reason, error}：status 必填；异常缺失时按 error 判定，
      // 无 error 才视为成功（不能把取消 / 预算超限一律显示成功）。
      const rawStatus = toStringValue(pick(payload, 'status'))
      const error = toStringValue(pick(payload, 'error', 'detail'))
      const status: AgentRun['status'] =
        rawStatus && rawStatus in AGENT_RUN_STATUS
          ? (rawStatus as AgentRun['status'])
          : error
            ? AGENT_RUN_STATUS.FAILED
            : AGENT_RUN_STATUS.SUCCEEDED
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_FINISHED,
        status,
        error,
      }
    }
    case AGENT_EVENT_TYPE.ERROR: {
      // 网关合成的上游中断帧（code=UPSTREAM_*）语义是「可续传」，不是 run 终态；
      // 标记 recoverable 供 application 层区分（其余 error 仍按终态失败处理）。
      const errorCode = toStringValue(pick(payload, 'code', 'error_code'))
      const errorMessage =
        toStringValue(pick(payload, 'message', 'detail', 'error')) ?? ''
      return {
        ...base,
        type: AGENT_EVENT_TYPE.ERROR,
        errorCode,
        errorMessage,
        recoverable: isRecoverableAgentErrorCode(errorCode),
      }
    }
    default:
      return null
  }
}
