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
  normalizeRunStatus,
  normalizeToolRisk,
  type AgentApproval,
  type AgentEventSourceRef,
  type AgentRun,
  type AgentRunEvent,
  type AgentRunInput,
  type AgentSession,
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

/** GET /agent/runs/{id} / POST /agent/runs/{id}/cancel 响应（agent_run 表字段） */
export interface AgentRunDto {
  id: string
  session_id?: string
  status?: string
  model?: string
  token_in?: number
  token_out?: number
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

/** 单条 SSE 事件原始帧（§11：run_id / sequence / type / timestamp + payload） */
export interface AgentEventDto {
  run_id?: string
  sequence?: number
  type?: string
  timestamp?: string
  payload?: Record<string, unknown>
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

/**
 * SSE 原始事件 → camelCase 领域事件。
 * 未识别的事件类型返回 null（忽略未知事件，不把未知载荷当已知结构渲染）。
 * payload 同时支持「顶层字段」与「payload 内字段」两种后端落法。
 */
export function toAgentRunEvent(dto: AgentEventDto): AgentRunEvent | null {
  const payload = isObject(dto.payload) ? dto.payload : {}
  const type = toStringValue(dto.type) ?? toStringValue(pick(payload, 'type'))
  const sequence = toFiniteNumber(dto.sequence ?? pick(payload, 'sequence'))
  if (!type || sequence === undefined) return null

  const base = {
    runId: toStringValue(dto.run_id ?? pick(payload, 'run_id')) ?? '',
    sequence,
    timestamp:
      toStringValue(dto.timestamp ?? pick(payload, 'timestamp')) ?? '',
  }

  switch (type) {
    case AGENT_EVENT_TYPE.RUN_STARTED:
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
        summary: toStringValue(pick(payload, 'summary', 'args_summary')),
      }
    }
    case AGENT_EVENT_TYPE.TOOL_RESULT: {
      const toolCallId = toStringValue(pick(payload, 'tool_call_id', 'toolCallId'))
      if (!toolCallId) return null
      const rawStatus = toStringValue(pick(payload, 'status'))
      const status =
        rawStatus === AGENT_TOOL_RESULT_STATUS.FAILED ||
        rawStatus === AGENT_TOOL_RESULT_STATUS.CANCELLED
          ? rawStatus
          : AGENT_TOOL_RESULT_STATUS.SUCCEEDED
      return {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_RESULT,
        toolCallId,
        status,
        summary: toStringValue(pick(payload, 'summary', 'result_summary')),
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
      const status = pick(payload, 'status')
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_FINISHED,
        status:
          typeof status === 'string' && status in AGENT_RUN_STATUS
            ? (status as AgentRun['status'])
            : AGENT_RUN_STATUS.SUCCEEDED,
        error: toStringValue(pick(payload, 'error', 'detail')),
      }
    }
    case AGENT_EVENT_TYPE.ERROR: {
      const errorMessage =
        toStringValue(pick(payload, 'message', 'detail', 'error')) ?? ''
      return {
        ...base,
        type: AGENT_EVENT_TYPE.ERROR,
        errorCode: toStringValue(pick(payload, 'code', 'error_code')),
        errorMessage,
      }
    }
    default:
      return null
  }
}
