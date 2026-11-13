/**
 * Agent DTO 与转换（infrastructure/dto 层——后端 snake_case 契约唯一出现层）。
 * 契约来源：doc/agent化/07_单Agent_Skills落地方案.md §10 数据模型 + §11 API 与 SSE；
 * 字段形态以 agent_service/interfaces/api/schemas.py 与 routes.py::_sse_frame 为唯一
 * 真实口径（INT-2519）：不保留早期草案 / 单测桩的多形态兼容分支，形态不符即报错。
 *
 * 架构红线：前端（domain / application / interfaces）只见 camelCase；
 * snake_case ↔ camelCase 只在此文件发生。
 */
import {
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_RESULT_STATUS,
  AGENT_TOOL_RISK,
  isRecoverableAgentErrorCode,
  normalizeRunStatus,
  normalizeToolRisk,
  type AgentApproval,
  type AgentApprovalDecisionResult,
  type AgentApprovalProposal,
  type AgentApprovalStatus,
  type AgentEventSourceRef,
  type AgentRun,
  type AgentRunBudget,
  type AgentRunEvent,
  type AgentRunInput,
  type AgentSession,
  type AgentSessionDetail,
  type AgentToolRisk,
} from '@/domain/models/agent'

/**
 * 后端契约不符（信封/字段形态漂移）。
 * 不静默回退：契约漂移必须显式失败，让页面落错误态并暴露真实原因，
 * 而不是表现成空列表 / 空事件。
 */
export class AgentContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AgentContractError'
  }
}

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

/** GET /agent/runs/{id}/approvals 响应（后端 routes.py::list_approvals 恒返 `{"items": [...]}`；M0 为空列表） */
export interface AgentApprovalsResponseDto {
  items: AgentApprovalDto[]
}

/** GET /agent/runs/{id} / POST /agent/runs/{id}/cancel 响应（agent_run 表字段，扁平） */
export interface AgentRunDto {
  id: string
  session_id?: string
  status?: string
  model?: string
  token_in?: number
  token_out?: number
  /** 预算上限（agent_run.budget；键与 agent_defaults.json 一致） */
  budget?: Record<string, unknown>
  created_at?: string
  started_at?: string
  finished_at?: string
  error?: string
}

/** GET /agent/runs/{id}/approvals 列表项（agent_approval 表字段） */
export interface AgentApprovalDto {
  id: string
  run_id?: string
  tool_call_id?: string
  status?: string
  proposal?: unknown
  diff?: unknown
  expires_at?: string
  decided_by?: number
  decided_at?: string
  created_at?: string
}

/** POST /agent/approvals/{id}/decision 请求体（后端 ApprovalDecisionRequest） */
export interface AgentApprovalDecisionDto {
  decision: string
}

/** POST /agent/approvals/{id}/decision 响应（后端 ApprovalDecisionResponse） */
export interface AgentApprovalDecisionResponseDto {
  approval: AgentApprovalDto
  run_status?: string
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
 * 真实形态（agent_service/routes.py::_sse_frame）：事件载荷的键与
 * run_id / sequence / type / timestamp **平铺在同一层**，没有嵌套 payload。
 */
export interface AgentEventDto {
  run_id?: string
  sequence?: number
  type?: string
  timestamp?: string
  [key: string]: unknown
}

function toStringValue(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function toFiniteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/** 无时区后缀的 ISO 时间戳（后端 `datetime.utcnow().isoformat()`）按 UTC 解释 */
const NAIVE_ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/

/**
 * 时间戳归一为带时区的 ISO。
 * 后端 agent_service 全部用 naive UTC（`utcnow().isoformat()` 无 `Z`），
 * 直接交给 `Date.parse` 会按**浏览器本地时区**解释 —— 在 UTC+8 会把审批单
 * 判成早 8 小时过期（INT-2472 实测：提案刚生成就显示「已过期」）。
 */
export function toUtcIso(value: unknown): string | undefined {
  const text = toStringValue(value)
  if (!text) return undefined
  return NAIVE_ISO_UTC.test(text) ? `${text}Z` : text
}

/** agent_run.budget（snake_case 上限键）→ 领域预算对象；全缺省返回 undefined */
export function toAgentBudget(value: unknown): AgentRunBudget | undefined {
  if (!isObject(value)) return undefined
  const budget: AgentRunBudget = {
    maxRounds: toFiniteNumber(value['max_rounds']),
    maxToolCalls: toFiniteNumber(value['max_tool_calls']),
    maxTokens: toFiniteNumber(value['max_tokens']),
    maxDurationSeconds: toFiniteNumber(value['max_duration_seconds']),
    maxOutputBytes: toFiniteNumber(value['max_output_bytes']),
  }
  return Object.values(budget).some((item) => item !== undefined)
    ? budget
    : undefined
}

/** snake_case sourceRefs → camelCase 域对象（非数组/字段缺失返回 undefined） */
export function toAgentSourceRefs(value: unknown): AgentEventSourceRef[] | undefined {
  if (!Array.isArray(value)) return undefined
  const refs: AgentEventSourceRef[] = []
  for (const item of value) {
    if (typeof item !== 'object' || item === null) continue
    const raw = item as Record<string, unknown>
    const reportId = toFiniteNumber(raw['report_id'])
    if (reportId === undefined) continue
    refs.push({
      reportId,
      metricId: toStringValue(raw['metric_id']),
      dataVersion: toStringValue(raw['data_version']),
      verified:
        typeof raw['verified'] === 'boolean'
          ? (raw['verified'] as boolean)
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
    createdAt: toUtcIso(dto.created_at),
    updatedAt: toUtcIso(dto.updated_at),
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
    budget: toAgentBudget(dto.budget),
    startedAt: toUtcIso(dto.started_at),
    finishedAt: toUtcIso(dto.finished_at),
    error: dto.error,
  }
}

/**
 * POST /agent/sessions/{id}/runs 响应解信封：真实后端为 `{run, created}`
 * （schemas.py::CreateRunResponse），网关透明转发不拆；解信封只在 infrastructure
 * 做（application 拿不到 run.id 会用 undefined 订阅事件流，服务端 run 继续跑成孤儿）。
 * 缺 run 视为契约错误直接抛，不回退成「把响应本身当 run」。
 */
export function toAgentRunFromCreateResponse(
  dto: AgentRunCreateResponseDto
): AgentRun {
  if (!isObject(dto) || !isObject(dto.run)) {
    throw new AgentContractError(
      '创建 Run 响应缺少 run 信封（期望 {run, created}）'
    )
  }
  return toAgentRun(dto.run)
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

/** GET /agent/runs/{id}/approvals 响应（真实 `{"items": [...]}`；裸数组视为契约错误） */
export function toAgentApprovals(dto: AgentApprovalsResponseDto): AgentApproval[] {
  if (!isObject(dto) || !Array.isArray(dto.items)) {
    throw new AgentContractError(
      '审批列表响应缺少 items 信封（期望 {"items": [...]}）'
    )
  }
  return dto.items.map(toAgentApproval)
}

/** 审批提案 snake_case → 领域对象（risk 缺失不降级为 READ：未知风险必须显式保留） */
export function toAgentApprovalProposal(
  value: unknown
): AgentApprovalProposal | undefined {
  if (!isObject(value)) return undefined
  const tool = toStringValue(value['tool'])
  if (!tool) return undefined
  const rawRisk = toStringValue(value['risk'])
  const risk: AgentToolRisk | undefined =
    rawRisk && rawRisk in AGENT_TOOL_RISK ? (rawRisk as AgentToolRisk) : undefined
  return {
    tool,
    risk,
    arguments: isObject(value['arguments'])
      ? (value['arguments'] as Record<string, unknown>)
      : undefined,
    argsHash: toStringValue(value['args_hash']),
    idempotencyKey: toStringValue(value['idempotency_key']),
    stepId: toStringValue(value['step_id']),
    turn: toFiniteNumber(value['turn']),
    requestedBy: toFiniteNumber(value['requested_by']),
    sessionId: toStringValue(value['session_id']),
  }
}

export function toAgentApproval(dto: AgentApprovalDto): AgentApproval {
  const status: AgentApprovalStatus =
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
    proposal: toAgentApprovalProposal(dto.proposal),
    diff: dto.diff,
    expiresAt: toUtcIso(dto.expires_at),
    decidedBy: toFiniteNumber(dto.decided_by),
    decidedAt: toUtcIso(dto.decided_at),
    createdAt: toUtcIso(dto.created_at),
  }
}

export function toAgentApprovalDecisionDto(
  decision: string
): AgentApprovalDecisionDto {
  return { decision }
}

/**
 * POST /agent/approvals/{id}/decision 响应解信封：`{approval, run_status}`
 * （后端 routes.py::decide_approval）。缺 approval 视为契约错误，不回退。
 */
export function toAgentApprovalDecisionResult(
  dto: AgentApprovalDecisionResponseDto
): AgentApprovalDecisionResult {
  if (!isObject(dto) || !isObject(dto.approval)) {
    throw new AgentContractError(
      '审批决策响应缺少 approval 信封（期望 {approval, run_status}）'
    )
  }
  return {
    approval: toAgentApproval(dto.approval as AgentApprovalDto),
    runStatus: normalizeRunStatus(dto.run_status),
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
 * SSE 原始事件 → camelCase 领域事件。
 * 只读真实帧的平铺 snake_case 键（routes.py::_sse_frame：事件载荷与
 * run_id/sequence/type/timestamp 同层，无嵌套 payload、无 camelCase 键）。
 * 未识别的事件类型返回 null（忽略未知事件，不把未知载荷当已知结构渲染）。
 */
export function toAgentRunEvent(dto: AgentEventDto): AgentRunEvent | null {
  const type = toStringValue(dto['type'])
  const sequence = toFiniteNumber(dto['sequence'])
  if (!type || sequence === undefined) return null

  const base = {
    runId: toStringValue(dto['run_id']) ?? '',
    sequence,
    timestamp: toUtcIso(dto['timestamp']) ?? '',
  }

  switch (type) {
    case AGENT_EVENT_TYPE.RUN_STARTED:
      // 后端 run_started 载荷为 {user_message, session_id, model, budget}，无 status；
      // 收到即代表 run 已受理进入执行，状态归一为 RUNNING。
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_STARTED,
        status: normalizeRunStatus(dto['status']),
        model: toStringValue(dto['model']),
        budget: toAgentBudget(dto['budget']),
      }
    case AGENT_EVENT_TYPE.MESSAGE_DELTA: {
      const messageId = toStringValue(dto['message_id'])
      if (!messageId) return null
      return {
        ...base,
        type: AGENT_EVENT_TYPE.MESSAGE_DELTA,
        messageId,
        delta: toStringValue(dto['delta']) ?? '',
      }
    }
    case AGENT_EVENT_TYPE.TOOL_CALL: {
      const toolCallId = toStringValue(dto['tool_call_id'])
      const tool = toStringValue(dto['tool'])
      if (!toolCallId || !tool) return null
      return {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_CALL,
        toolCallId,
        tool,
        risk: normalizeToolRisk(dto['risk']),
        summary: summarizeToolArguments(dto['arguments']),
      }
    }
    case AGENT_EVENT_TYPE.TOOL_RESULT: {
      const toolCallId = toStringValue(dto['tool_call_id'])
      if (!toolCallId) return null
      const rawStatus = toStringValue(dto['status'])
      const ok = dto['ok']
      // 真实载荷为 {ok, content, error_code}，没有 status；ok=false → FAILED。
      const status =
        rawStatus === AGENT_TOOL_RESULT_STATUS.FAILED ||
        rawStatus === AGENT_TOOL_RESULT_STATUS.CANCELLED
          ? rawStatus
          : typeof ok === 'boolean' && !ok
            ? AGENT_TOOL_RESULT_STATUS.FAILED
            : AGENT_TOOL_RESULT_STATUS.SUCCEEDED
      const errorCode = toStringValue(dto['error_code'])
      return {
        ...base,
        type: AGENT_EVENT_TYPE.TOOL_RESULT,
        toolCallId,
        status,
        summary: clampText(
          toStringValue(dto['content']) ?? errorCode,
          TOOL_RESULT_SUMMARY_MAX_CHARS
        ),
        errorCode,
        sourceRefs: toAgentSourceRefs(dto['source_refs']),
      }
    }
    case AGENT_EVENT_TYPE.APPROVAL_REQUIRED: {
      const approvalId = toStringValue(dto['approval_id'])
      if (!approvalId) return null
      const rawRisk = toStringValue(dto['risk'])
      return {
        ...base,
        type: AGENT_EVENT_TYPE.APPROVAL_REQUIRED,
        approvalId,
        toolCallId: toStringValue(dto['tool_call_id']),
        tool: toStringValue(dto['tool']),
        risk:
          rawRisk && rawRisk in AGENT_TOOL_RISK
            ? (rawRisk as AgentToolRisk)
            : undefined,
        expiresAt: toUtcIso(dto['expires_at']),
        proposal: toAgentApprovalProposal(dto['proposal']),
      }
    }
    case AGENT_EVENT_TYPE.CONTEXT_COMPACTED:
      // 真实载荷（context_assembler）：level / snapshot_version / token_count_before /
      // token_count_after / dropped_count / debug；debug 开启才附被裁消息与备忘。
      return {
        ...base,
        type: AGENT_EVENT_TYPE.CONTEXT_COMPACTED,
        level: toStringValue(dto['level']),
        snapshotVersion: toFiniteNumber(dto['snapshot_version']),
        tokenCountBefore: toFiniteNumber(dto['token_count_before']),
        tokenCountAfter: toFiniteNumber(dto['token_count_after']),
        droppedCount: toFiniteNumber(dto['dropped_count']),
        debug: dto['debug'] === true,
      }
    case AGENT_EVENT_TYPE.RUN_FINISHED: {
      // 真实载荷 {status, reason, error}：status 必填；异常缺失时按 error 判定，
      // 无 error 才视为成功（不能把取消 / 预算超限一律显示成功）。
      const rawStatus = toStringValue(dto['status'])
      const error = toStringValue(dto['error'])
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
      const errorCode = toStringValue(dto['code'])
      return {
        ...base,
        type: AGENT_EVENT_TYPE.ERROR,
        errorCode,
        errorMessage: toStringValue(dto['message']) ?? '',
        recoverable: isRecoverableAgentErrorCode(errorCode),
      }
    }
    default:
      return null
  }
}
