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
  AGENT_BUDGET_DIMENSION,
  AGENT_EVENT_TYPE,
  AGENT_RUN_STATUS,
  AGENT_TOOL_RESULT_STATUS,
  AGENT_TOOL_RISK,
  isRecoverableAgentErrorCode,
  normalizePauseReason,
  normalizeRunMode,
  normalizeRunStatus,
  normalizeToolRisk,
  type AgentApproval,
  type AgentApprovalDecisionResult,
  type AgentApprovalObjectRef,
  type AgentApprovalProposal,
  type AgentApprovalStatus,
  type AgentAutoArtifact,
  type AgentAutoPause,
  type AgentAutoProgress,
  type AgentAutoStepPhase,
  type AgentAutoUsage,
  type AgentBudgetDimension,
  type AgentEventSourceRef,
  type AgentRun,
  type AgentRunBudget,
  type AgentRunEvent,
  type AgentRunInput,
  type AgentRunPausePolicy,
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
  /**
   * 运行模式（INT-2474）：chat（默认）/ auto。字段缺省即 chat，
   * 普通对话不带此键（Auto 关闭不影响普通对话）。
   */
  mode?: string
  /**
   * 请求侧收紧预算（键同 RunBudget 蛇形键；只能收紧，0 / 负数视为不覆盖，
   * 未知键服务端 400 INVALID_BUDGET）。
   */
  budget?: Record<string, number>
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
  /** 运行模式（INT-2474 RunResponse.mode：chat / auto） */
  mode?: string
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
  /**
   * §9.4.1 拆单批次字段（后端 ApprovalResponse）：一次 tool call 影响 >20 对象
   * 时拆成 N 张单，同批共享 `batch_id`，`batch_index` 1..N；未拆单时
   * `batch_id` 为空、`batch_index` / `batch_total` 为 1。
   */
  batch_id?: string | null
  batch_index?: number
  batch_total?: number
  /** 本单对象摘要 `{kind, ids}`（拆单时已收窄到本单对象） */
  object_ref?: AgentApprovalObjectRefDto | null
}

/** object_ref 原始形态：对象类型 + 对象 id 列表（非枚举范围 ids 为空） */
export interface AgentApprovalObjectRefDto {
  kind?: string
  ids?: unknown[]
}

/** POST /agent/approvals/{id}/decision 请求体（后端 ApprovalDecisionRequest） */
export interface AgentApprovalDecisionDto {
  decision: string
  /**
   * 破坏性操作二次确认（INT-2467）：DESTRUCTIVE 的 APPROVE 必须带 true，
   * 拒绝不需要；WRITE 不带（缺省 false），与后端语义一致。
   */
  confirm?: boolean
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

/** 字符串数组（缺失 / 非数组返回空列表；剔除非字符串项） */
function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => toStringValue(item))
    .filter((item): item is string => Boolean(item))
}

/** 领域预算对象 → 请求体蛇形键（只带显式给出且 > 0 的维度；0 / 负数视为不覆盖） */
export function toAgentBudgetRequestDto(
  budget: AgentRunBudget | undefined
): Record<string, number> | undefined {
  if (!budget) return undefined
  const dto: Record<string, number> = {}
  const pairs: Array<[AgentBudgetDimension, number | undefined]> = [
    [AGENT_BUDGET_DIMENSION.ROUNDS, budget.maxRounds],
    [AGENT_BUDGET_DIMENSION.TOOL_CALLS, budget.maxToolCalls],
    [AGENT_BUDGET_DIMENSION.TOKENS, budget.maxTokens],
    [AGENT_BUDGET_DIMENSION.DURATION, budget.maxDurationSeconds],
    [AGENT_BUDGET_DIMENSION.OUTPUT, budget.maxOutputBytes],
  ]
  const snakeKeys: Record<AgentBudgetDimension, string> = {
    maxRounds: 'max_rounds',
    maxToolCalls: 'max_tool_calls',
    maxTokens: 'max_tokens',
    maxDurationSeconds: 'max_duration_seconds',
    maxOutputBytes: 'max_output_bytes',
  }
  for (const [key, value] of pairs) {
    if (value === undefined || !Number.isFinite(value) || value <= 0) continue
    dto[snakeKeys[key]] = Math.trunc(value)
  }
  return Object.keys(dto).length > 0 ? dto : undefined
}

/** run_started.payload.pause_policy（仅 Auto）→ 领域暂停策略 */
export function toAgentPausePolicy(value: unknown): AgentRunPausePolicy | undefined {
  if (!isObject(value)) return undefined
  const budgetRatio = toFiniteNumber(value['budget_ratio'])
  const consecutiveFailures = toFiniteNumber(value['consecutive_failures'])
  if (budgetRatio === undefined && consecutiveFailures === undefined) return undefined
  return { budgetRatio, consecutiveFailures }
}

/** auto_step / run_paused 载荷的 usage → 领域用量（缺字段按 0，不让展示层出现 NaN） */
export function toAgentAutoUsage(value: unknown): AgentAutoUsage {
  const raw = isObject(value) ? value : {}
  return {
    rounds: toFiniteNumber(raw['rounds']) ?? 0,
    toolCalls: toFiniteNumber(raw['tool_calls']) ?? 0,
    tokens: toFiniteNumber(raw['tokens']) ?? 0,
    elapsedSeconds: toFiniteNumber(raw['elapsed_seconds']) ?? 0,
    outputBytes: toFiniteNumber(raw['output_bytes']) ?? 0,
  }
}

/** auto_step.payload.ratios → 各维度消耗比（未知维度丢弃；未启用维度不在表内） */
function toAgentBudgetRatios(
  value: unknown
): Partial<Record<AgentBudgetDimension, number>> | undefined {
  if (!isObject(value)) return undefined
  const ratios: Partial<Record<AgentBudgetDimension, number>> = {}
  const known: Record<string, AgentBudgetDimension> = {
    max_rounds: AGENT_BUDGET_DIMENSION.ROUNDS,
    max_tool_calls: AGENT_BUDGET_DIMENSION.TOOL_CALLS,
    max_tokens: AGENT_BUDGET_DIMENSION.TOKENS,
    max_duration_seconds: AGENT_BUDGET_DIMENSION.DURATION,
    max_output_bytes: AGENT_BUDGET_DIMENSION.OUTPUT,
  }
  for (const [rawKey, dimension] of Object.entries(known)) {
    const ratio = toFiniteNumber(value[rawKey])
    if (ratio !== undefined) ratios[dimension] = ratio
  }
  return Object.keys(ratios).length > 0 ? ratios : undefined
}

/** auto_step.payload.artifacts → 产物摘要（非数组 / 缺 id 的条目丢弃） */
function toAgentAutoArtifacts(value: unknown): AgentAutoArtifact[] {
  if (!Array.isArray(value)) return []
  const artifacts: AgentAutoArtifact[] = []
  for (const item of value) {
    if (!isObject(item)) continue
    const id = toStringValue(item['id'])
    if (!id) continue
    artifacts.push({
      id,
      kind: toStringValue(item['kind']) ?? '',
      uri: toStringValue(item['uri']) ?? '',
    })
  }
  return artifacts
}

/** auto_step 载荷 → 领域进度快照（step 缺失视为契约不符，返回 null 丢弃该事件） */
export function toAgentAutoProgress(value: unknown): AgentAutoProgress | null {
  if (!isObject(value)) return null
  const step = toFiniteNumber(value['step'])
  if (step === undefined) return null
  const phase = toStringValue(value['phase'])
  return {
    step,
    turn: toFiniteNumber(value['turn']),
    phase: phase as AgentAutoStepPhase | undefined,
    goal: toStringValue(value['goal']),
    plan: toStringValue(value['plan']),
    usage: toAgentAutoUsage(value['usage']),
    limits: toAgentBudget(value['limits']),
    ratios: toAgentBudgetRatios(value['ratios']),
    ratio: toFiniteNumber(value['ratio']) ?? 0,
    consecutiveFailures: toFiniteNumber(value['consecutive_failures']) ?? 0,
    idleNudges: toFiniteNumber(value['idle_nudges']),
    artifactCount:
      toFiniteNumber(value['artifact_count']) ??
      toAgentAutoArtifacts(value['artifacts']).length,
    artifacts: toAgentAutoArtifacts(value['artifacts']),
    instruction: toStringValue(value['instruction']),
    pauseReason: normalizePauseReason(value['pause_reason']),
  }
}

/** run_paused 载荷 → 暂停事实（策略阈值随事件下发，用于展示「暂停点」） */
export function toAgentAutoPause(value: unknown): AgentAutoPause {
  const raw = isObject(value) ? value : {}
  return {
    reason: normalizePauseReason(raw['reason']),
    usage: isObject(raw['usage']) ? toAgentAutoUsage(raw['usage']) : undefined,
    limits: toAgentBudget(raw['limits']),
    ratio: toFiniteNumber(raw['ratio']),
    consecutiveFailures: toFiniteNumber(raw['consecutive_failures']) ?? 0,
    policy: {
      budgetRatio: toFiniteNumber(raw['pause_budget_ratio']),
      consecutiveFailures: toFiniteNumber(raw['pause_consecutive_failures']),
    },
    at: toUtcIso(raw['timestamp']),
  }
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
    // mode 缺省按 chat（旧 run 无该字段；只在 Auto 才需要区分展示）
    mode: dto.mode === undefined ? undefined : normalizeRunMode(dto.mode),
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
    /** §9.4.1：本批总对象数（拆单后每张单都带批次总数） */
    objectCount: toFiniteNumber(value['object_count']),
  }
}

/**
 * object_ref（`{kind, ids}`）→ 领域对象摘要。
 * ids 元素统一转字符串（后端可能是数字 id）；kind 与 ids 都缺时返回 undefined，
 * 不伪造空摘要。非枚举范围的 ids 为空数组但保留 kind（展示「按范围执行」）。
 */
export function toAgentApprovalObjectRef(
  value: unknown
): AgentApprovalObjectRef | undefined {
  if (!isObject(value)) return undefined
  const kind = toStringValue(value['kind'])
  const rawIds = Array.isArray(value['ids']) ? value['ids'] : []
  const ids = rawIds
    .map((id) => toStringValue(id))
    .filter((id): id is string => Boolean(id))
  if (!kind && ids.length === 0) return undefined
  return { kind, ids }
}

/** 批次序号 / 总数归一：缺省或非法值按单张（1）兼容 */
function toBatchCount(value: unknown, fallback: number): number {
  const number = toFiniteNumber(value)
  return number !== undefined && Number.isInteger(number) && number >= 1
    ? number
    : fallback
}

export function toAgentApproval(dto: AgentApprovalDto): AgentApproval {
  const status: AgentApprovalStatus =
    dto.status === 'APPROVED' ||
    dto.status === 'REJECTED' ||
    dto.status === 'EXPIRED'
      ? dto.status
      : 'PENDING'
  const batchTotal = toBatchCount(dto.batch_total, 1)
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
    // 旧单 / 缺字段按单张口径：batchId 为空、序号与总数都是 1
    batchId: toStringValue(dto.batch_id) || undefined,
    batchIndex: toBatchCount(dto.batch_index, 1),
    batchTotal,
    objectRef: toAgentApprovalObjectRef(dto.object_ref),
  }
}

export function toAgentApprovalDecisionDto(
  decision: string,
  confirm = false
): AgentApprovalDecisionDto {
  // 只有显式二次确认才带 confirm：WRITE / REJECT 的请求体保持 `{decision}`
  // 单口径，避免前端多发一个后端并不需要的字段。
  return confirm ? { decision, confirm: true } : { decision }
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
  const dto: AgentRunCreateDto = { message: input.message }
  // 只有 Auto 才带 mode / budget：普通对话保持 `{message}` 单口径（Auto 关闭不影响普通对话）
  if (input.mode === 'auto') {
    dto.mode = 'auto'
    const budget = toAgentBudgetRequestDto(input.budget)
    if (budget) dto.budget = budget
  }
  return dto
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
      // 后端 run_started 载荷为 {user_message, session_id, model, budget, mode,
      // pause_policy?}，无 status；收到即代表 run 已受理进入执行，状态归一为 RUNNING。
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_STARTED,
        status: normalizeRunStatus(dto['status']),
        model: toStringValue(dto['model']),
        budget: toAgentBudget(dto['budget']),
        mode: normalizeRunMode(dto['mode']),
        pausePolicy: toAgentPausePolicy(dto['pause_policy']),
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
        // §9.4.1 第 10 条：每张单一条 approval_required，同批 tool_call_id 相同；
        // 未拆单时字段缺省（按单张渲染）。
        batchId: toStringValue(dto['batch_id']) || undefined,
        batchIndex: toFiniteNumber(dto['batch_index']),
        batchTotal: toFiniteNumber(dto['batch_total']),
      }
    }
    case AGENT_EVENT_TYPE.AUTO_STEP: {
      // 真实载荷（auto_mode.AutoModeController.progress_payload）平铺在本帧：
      // step / turn / phase / goal / plan / usage / limits / ratios / ratio /
      // consecutive_failures / artifact_count / artifacts / instruction? / pause_reason?
      const progress = toAgentAutoProgress(dto)
      if (!progress) return null
      return { ...base, type: AGENT_EVENT_TYPE.AUTO_STEP, progress }
    }
    case AGENT_EVENT_TYPE.RUN_PAUSED:
      // reason ∈ {budget_threshold, consecutive_tool_failures} + 当时用量与策略阈值
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_PAUSED,
        pause: toAgentAutoPause(dto),
      }
    case AGENT_EVENT_TYPE.RUN_RESUMED:
      return {
        ...base,
        type: AGENT_EVENT_TYPE.RUN_RESUMED,
        pauseReason: normalizePauseReason(dto['pause_reason']),
        ackedBudgetPause: dto['acked_budget_pause'] === true,
        consecutiveFailures: toFiniteNumber(dto['consecutive_failures']),
        budget: toAgentBudget(dto['budget']),
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
    case AGENT_EVENT_TYPE.SKILL_DRAFT_SUGGESTED: {
      // 载荷 {suggested_name, description, tools_used, source_skill, created,
      // requires_confirmation}；没有 name 的建议无法落成草稿，按未知事件忽略。
      const suggestedName = toStringValue(dto['suggested_name'])
      if (!suggestedName) return null
      return {
        ...base,
        type: AGENT_EVENT_TYPE.SKILL_DRAFT_SUGGESTED,
        suggestedName,
        description: toStringValue(dto['description']) ?? '',
        toolsUsed: toStringList(dto['tools_used']),
        sourceSkill: toStringValue(dto['source_skill']),
        created: dto['created'] === true,
        requiresConfirmation: dto['requires_confirmation'] !== false,
      }
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
