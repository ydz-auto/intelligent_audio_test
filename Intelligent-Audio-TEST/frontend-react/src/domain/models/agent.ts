/**
 * Agent 会话 / Run / 事件领域模型（domain 层；doc/agent化/07_单Agent_Skills落地方案.md
 * §5.3 枚举、§9.1 状态机、§9.2 断点续跑、§11 API 与 SSE）。
 *
 * 架构红线：domain 只见 camelCase 领域对象；后端 snake_case 契约的转换只发生在
 * infrastructure/dto/agent.dto.ts。枚举一律常量化（禁止魔法字符串）。
 */

/**
 * 工具中文显示名映射（§3.4 表）。
 * 归 domain：application 层的 run 事件 → 工具卡补丁（agent-run-store）与界面工具卡
 * 共用同一份文案，避免 application 反向依赖 features（INT-2507 收敛单实例时迁移）。
 */
export const AGENT_TOOL_LABELS: Record<string, string> = {
  report_get_facts: '读取报告数据',
  report_query_metrics: '查询报告指标',
  studio_create_draft: '创建报告草稿',
  studio_apply_edit: '修改文档',
  studio_insert_chart: '插入图表',
  studio_get_versions: '查询历史版本',
  studio_restore_version: '恢复历史版本',
  studio_request_export: '导出文档',
  compare_reports: '对比报告',
  secondary_compare_reports: '二次对比',
}

/** RunStatus 枚举（§5.3；后端原值即大写字符串，禁止改口径） */
export const AGENT_RUN_STATUS = {
  QUEUED: 'QUEUED',
  RUNNING: 'RUNNING',
  WAITING_APPROVAL: 'WAITING_APPROVAL',
  SUCCEEDED: 'SUCCEEDED',
  FAILED: 'FAILED',
  CANCELLED: 'CANCELLED',
  BUDGET_EXCEEDED: 'BUDGET_EXCEEDED',
} as const

export type AgentRunStatus =
  (typeof AGENT_RUN_STATUS)[keyof typeof AGENT_RUN_STATUS]

/** RunStatus → 中文徽标（消息终态徽标与运行时间线共用，单一事实源） */
export const AGENT_RUN_STATUS_LABELS: Record<AgentRunStatus, string> = {
  QUEUED: '排队中',
  RUNNING: '运行中',
  WAITING_APPROVAL: '等待审批',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  BUDGET_EXCEEDED: '超出预算',
}

/** 终态集合（§9.1 状态机；进入终态后事件流可关闭，不再重连） */
const TERMINAL_RUN_STATUSES: ReadonlySet<string> = new Set([
  AGENT_RUN_STATUS.SUCCEEDED,
  AGENT_RUN_STATUS.FAILED,
  AGENT_RUN_STATUS.CANCELLED,
  AGENT_RUN_STATUS.BUDGET_EXCEEDED,
])

export function isTerminalRunStatus(status: AgentRunStatus): boolean {
  return TERMINAL_RUN_STATUSES.has(status)
}

/** 未识别状态（后端新增枚举值）归一为 RUNNING 之外的中性值，调用方按「进行中」处理 */
export function normalizeRunStatus(value: unknown): AgentRunStatus {
  if (typeof value === 'string' && value in AGENT_RUN_STATUS) {
    return value as AgentRunStatus
  }
  return AGENT_RUN_STATUS.RUNNING
}

/** SSE 事件类型枚举（§5.3 EventType；后端原值小写蛇形） */
export const AGENT_EVENT_TYPE = {
  RUN_STARTED: 'run_started',
  MESSAGE_DELTA: 'message_delta',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  APPROVAL_REQUIRED: 'approval_required',
  CONTEXT_COMPACTED: 'context_compacted',
  /** run 正常结束且本次调用 ≥2 个工具时下发的「沉淀为 Skill」草案建议（不落库） */
  SKILL_DRAFT_SUGGESTED: 'skill_draft_suggested',
  /** Auto 模式每轮进度（当前步骤 / 预算水位 / 产物；INT-2474 §9.4） */
  AUTO_STEP: 'auto_step',
  /** Auto 暂停（预算到阈值 / 连续工具失败；run 转 WAITING_APPROVAL） */
  RUN_PAUSED: 'run_paused',
  /** 用户确认继续（POST /agent/runs/{id}/resume） */
  RUN_RESUMED: 'run_resumed',
  RUN_FINISHED: 'run_finished',
  ERROR: 'error',
} as const

export type AgentEventType =
  (typeof AGENT_EVENT_TYPE)[keyof typeof AGENT_EVENT_TYPE]

/** 工具风险等级（§5.3 ToolRisk） */
export const AGENT_TOOL_RISK = {
  READ: 'READ',
  WRITE: 'WRITE',
  DESTRUCTIVE: 'DESTRUCTIVE',
} as const

export type AgentToolRisk =
  (typeof AGENT_TOOL_RISK)[keyof typeof AGENT_TOOL_RISK]

/** 风险等级中文名（审批卡 / 工具卡共用；§9.4：DESTRUCTIVE 永远单条） */
export const AGENT_TOOL_RISK_LABELS: Record<AgentToolRisk, string> = {
  READ: '只读',
  WRITE: '写操作',
  DESTRUCTIVE: '高危操作',
}

export function normalizeToolRisk(value: unknown): AgentToolRisk {
  if (typeof value === 'string' && value in AGENT_TOOL_RISK) {
    return value as AgentToolRisk
  }
  return AGENT_TOOL_RISK.READ
}

/** 工具执行结果状态（tool_result 载荷；只认三种，未知按失败处理） */
export const AGENT_TOOL_RESULT_STATUS = {
  SUCCEEDED: 'SUCCEEDED',
  FAILED: 'FAILED',
  CANCELLED: 'CANCELLED',
} as const

export type AgentToolResultStatus =
  (typeof AGENT_TOOL_RESULT_STATUS)[keyof typeof AGENT_TOOL_RESULT_STATUS]

/** Agent 会话（agent_session 表；§10 数据模型） */
export interface AgentSession {
  id: string
  title: string
  /** 会话当前激活 Skill（L2 正文已注入；仅展示用） */
  activeSkill?: string
  model?: string
  createdAt?: string
  updatedAt?: string
}

/** Agent Run（agent_run 表；§10 数据模型） */
export interface AgentRun {
  id: string
  sessionId: string
  status: AgentRunStatus
  /** 运行模式（INT-2474：chat / auto；缺省按 chat） */
  mode?: AgentRunMode
  model?: string
  tokenIn?: number
  tokenOut?: number
  /** 本轮预算上限（§9.3；时间线展示预算消耗用） */
  budget?: AgentRunBudget
  startedAt?: string
  finishedAt?: string
  error?: string
}

/** 会话历史消息（GET /agent/sessions/{id} 的 messages 项） */
export interface AgentSessionMessage {
  role: string
  content: string
  toolCallId?: string
}

/** 会话详情（GET /agent/sessions/{id}：`{session, messages, runs}` 信封） */
export interface AgentSessionDetail {
  session: AgentSession
  messages: AgentSessionMessage[]
  runs: AgentRun[]
}

/** 审批单状态（§10 agent_approval.status；后端原值即大写字符串） */
export const AGENT_APPROVAL_STATUS = {
  PENDING: 'PENDING',
  APPROVED: 'APPROVED',
  REJECTED: 'REJECTED',
  EXPIRED: 'EXPIRED',
} as const

export type AgentApprovalStatus =
  (typeof AGENT_APPROVAL_STATUS)[keyof typeof AGENT_APPROVAL_STATUS]

export function isPendingApprovalStatus(status: AgentApprovalStatus): boolean {
  return status === AGENT_APPROVAL_STATUS.PENDING
}

/**
 * 审批单是否已过期（本地倒计时口径）。
 * 服务端到点也会拒绝决策（409），这里只用于「到点即禁用按钮 / 卡片失效」的即时反馈；
 * 状态字段仍以服务端列表为准。
 */
export function isApprovalExpired(
  approval: Pick<AgentApproval, 'status' | 'expiresAt'>,
  now: number = Date.now()
): boolean {
  if (approval.status !== AGENT_APPROVAL_STATUS.PENDING) return false
  if (!approval.expiresAt) return false
  const expiresAt = Date.parse(approval.expiresAt)
  return Number.isFinite(expiresAt) && expiresAt <= now
}

/** 审批决议（POST /agent/approvals/{id}/decision；后端大小写不敏感，这里恒发大写） */
export const AGENT_APPROVAL_DECISION = {
  APPROVE: 'APPROVE',
  REJECT: 'REJECT',
} as const

export type AgentApprovalDecision =
  (typeof AGENT_APPROVAL_DECISION)[keyof typeof AGENT_APPROVAL_DECISION]

/**
 * 审批决策的 agent_service 字符串业务码（INT-2472 P1）。
 * `ApiError.code` 只收平台数字码，字符串码保留在 `ApiError.rawCode`。
 */
export const AGENT_APPROVAL_ERROR_CODE = {
  /** DESTRUCTIVE 批准缺 confirm（400）：决策未落库，可带 confirm=true 重发 */
  CONFIRMATION_REQUIRED: 'APPROVAL_CONFIRMATION_REQUIRED',
} as const

/** 审批单同时影响的对象数上限（§9.4：单次影响 >20 对象必须单条审批） */
export const AGENT_APPROVAL_OBJECT_LIMIT = 20

/**
 * 审批单负责的对象摘要（§9.4.1 `object_ref = {kind, ids}`）。
 * 拆单后每张单的 ids 已由后端收窄到本单负责的对象；未拆单时是整次调用的对象。
 * 非枚举范围（`mode=all` / `failed_only`）按 1 个对象计，此时 ids 为空但 kind 仍在。
 */
export interface AgentApprovalObjectRef {
  /** 对象类型（后端 object_ref.kind：testcase / audio / task / device …） */
  kind?: string
  /** 本单负责的对象 id（字符串化展示） */
  ids: string[]
}

/**
 * 审批提案（后端 ApprovalService.propose 落库形态）：
 * `tool` / `risk` / `arguments` / `args_hash` / `idempotency_key` / `step_id` /
 * `turn` / `requested_by` / `session_id`。arguments 已由后端脱敏，前端只展示不执行。
 */
export interface AgentApprovalProposal {
  tool: string
  /** 风险等级（后端缺省时 undefined：不能把未知风险降级成 READ） */
  risk?: AgentToolRisk
  arguments?: Record<string, unknown>
  argsHash?: string
  idempotencyKey?: string
  /** 归属步骤 id：计划级批量展示按它分组（§9.4） */
  stepId?: string
  turn?: number
  requestedBy?: number
  sessionId?: string
  /**
   * 本批总对象数（§9.4.1 proposal.object_count）：拆单后每张单都带批次总数，
   * 非枚举范围计 1。拆单前 / 旧提案无此字段。
   */
  objectCount?: number
}

/** 待审批提案（§10 agent_approval；M2 审批卡实现 + §9.4.1 拆单批次） */
export interface AgentApproval {
  id: string
  runId: string
  toolCallId?: string
  status: AgentApprovalStatus
  /** 提案正文（含工具、风险、脱敏参数） */
  proposal?: AgentApprovalProposal
  /** 变更预览（REST 写工具为 {kind:'rest_request',method,path,arguments}；域写工具可覆盖） */
  diff?: unknown
  /** 过期时间（ISO；到点即不可再批准，服务端 409 兜底） */
  expiresAt?: string
  /** 决策人（用户 id；后端 decided_by） */
  decidedBy?: number
  /** 决策时间（ISO；后端 decided_at） */
  decidedAt?: string
  createdAt?: string
  /**
   * 拆单批次 id（§9.4.1）：一次 tool call 影响 >20 对象时拆成 N 张单，同批共享；
   * 未拆单为空。旧单 / 缺字段按单张处理（batchTotal 缺省 1）。
   */
  batchId?: string
  /** 本单在本批中的序号（1 起；未拆单为 1） */
  batchIndex?: number
  /** 本批总单数（未拆单 / 旧单为 1） */
  batchTotal?: number
  /** 本单对象摘要（§9.4.1 object_ref；拆单时已收窄到本单） */
  objectRef?: AgentApprovalObjectRef
}

/** Run 预算（§9.3/§9.4；后端 agent_run.budget，字段名与配置一致） */
export interface AgentRunBudget {
  maxRounds?: number
  maxToolCalls?: number
  maxTokens?: number
  maxDurationSeconds?: number
  maxOutputBytes?: number
}

/** 预算维度（领域键；creation 请求与进度展示共用，禁止散落字符串） */
export const AGENT_BUDGET_DIMENSION = {
  ROUNDS: 'maxRounds',
  TOOL_CALLS: 'maxToolCalls',
  TOKENS: 'maxTokens',
  DURATION: 'maxDurationSeconds',
  OUTPUT: 'maxOutputBytes',
} as const

export type AgentBudgetDimension =
  (typeof AGENT_BUDGET_DIMENSION)[keyof typeof AGENT_BUDGET_DIMENSION]

/** 预算维度中文名（Auto 预算设置与进度面板共用） */
export const AGENT_BUDGET_DIMENSION_LABELS: Record<AgentBudgetDimension, string> = {
  maxRounds: '轮次',
  maxToolCalls: '工具调用',
  maxTokens: 'token',
  maxDurationSeconds: '时长',
  // 展示单位统一为 MB（auto-progress.ts 换算），标签不再写「字节」，避免「输出字节 0 / 20 MB」
  maxOutputBytes: '最大输出',
}

/**
 * Run 运行模式（INT-2474 §9.4）：
 * - chat：单轮问答（默认，普通对话不受 Auto 影响）；
 * - auto：目标驱动长任务（预算约束 + 进度汇报 + 暂停继续）。
 */
export const AGENT_RUN_MODE = {
  CHAT: 'chat',
  AUTO: 'auto',
} as const

export type AgentRunMode = (typeof AGENT_RUN_MODE)[keyof typeof AGENT_RUN_MODE]

export function normalizeRunMode(value: unknown): AgentRunMode {
  return value === AGENT_RUN_MODE.AUTO ? AGENT_RUN_MODE.AUTO : AGENT_RUN_MODE.CHAT
}

/** Auto 暂停原因（run_paused.payload.reason；§9.4） */
export const AGENT_RUN_PAUSE_REASON = {
  /** 预算消耗到暂停比例（默认 80%） */
  BUDGET_THRESHOLD: 'budget_threshold',
  /** 连续工具失败到暂停阈值（默认 2 次） */
  CONSECUTIVE_TOOL_FAILURES: 'consecutive_tool_failures',
} as const

export type AgentRunPauseReason =
  (typeof AGENT_RUN_PAUSE_REASON)[keyof typeof AGENT_RUN_PAUSE_REASON]

export function normalizePauseReason(value: unknown): AgentRunPauseReason | undefined {
  // 键名（BUDGET_THRESHOLD）与后端原值（budget_threshold）不同，必须按值匹配
  return typeof value === 'string' &&
    (Object.values(AGENT_RUN_PAUSE_REASON) as string[]).includes(value)
    ? (value as AgentRunPauseReason)
    : undefined
}

/** Auto 暂停策略（run_started.payload.pause_policy；启动前展示「何时会暂停」） */
export interface AgentRunPausePolicy {
  /** 预算消耗比例阈值（0–1；默认 0.8） */
  budgetRatio?: number
  /** 连续工具失败阈值（默认 2） */
  consecutiveFailures?: number
}

/** Auto 步进阶段（auto_step.payload.phase） */
export const AGENT_AUTO_STEP_PHASE = {
  STEP: 'step',
  CONTINUE: 'continue',
  RESUME: 'resume',
} as const

export type AgentAutoStepPhase =
  (typeof AGENT_AUTO_STEP_PHASE)[keyof typeof AGENT_AUTO_STEP_PHASE]

/** Auto 预算水位用量（auto_step.payload.usage） */
export interface AgentAutoUsage {
  rounds: number
  toolCalls: number
  tokens: number
  elapsedSeconds: number
  outputBytes: number
}

/** Auto 已产出的工件摘要（只含 id / kind / uri，不含正文） */
export interface AgentAutoArtifact {
  id: string
  kind: string
  uri: string
}

/**
 * Auto 进度快照（auto_step 事件归约；进度时间线 / 预算水位 / 产物）。
 * 后端每轮一条，`phase` 标明本轮是正常步进、续跑提示还是用户确认继续。
 */
export interface AgentAutoProgress {
  step: number
  turn?: number
  phase?: AgentAutoStepPhase
  /** 目标（用户原始目标，模型首轮计划可能收窄） */
  goal?: string
  /** 当前计划（模型首轮写入 scratchpad.plan，随进度下发） */
  plan?: string
  usage: AgentAutoUsage
  limits?: AgentRunBudget
  /** 各维度消耗比（0–1；未启用的维度不在表内） */
  ratios?: Partial<Record<AgentBudgetDimension, number>>
  /** 最高维度消耗比 */
  ratio: number
  consecutiveFailures: number
  /** 累计空转提示次数（重启恢复用，展示层忽略） */
  idleNudges?: number
  artifactCount: number
  artifacts: AgentAutoArtifact[]
  /** 续跑提示（continue / resume 两相另带；展示为「已回灌模型」提示） */
  instruction?: string
  pauseReason?: AgentRunPauseReason
}

/** Auto 暂停事实（run_paused 事件；run_resumed 后清空） */
export interface AgentAutoPause {
  reason?: AgentRunPauseReason
  /** 暂停时的预算水位（可能与最近一条 auto_step 相同或更新） */
  usage?: AgentAutoUsage
  limits?: AgentRunBudget
  ratio?: number
  consecutiveFailures: number
  /** 暂停策略（服务端在 run_paused 载荷里带同一份阈值；刷新恢复的占位事实缺省） */
  policy?: AgentRunPausePolicy
  at?: string
}

/** 审批决策结果（POST /agent/approvals/{id}/decision 的 {approval, run_status}） */
export interface AgentApprovalDecisionResult {
  approval: AgentApproval
  runStatus: AgentRunStatus
}

/** 事件来源引用（sourceRefs；报告 ID + 指标 ID + 数据版本） */
export interface AgentEventSourceRef {
  reportId: number
  metricId?: string
  dataVersion?: string
  verified?: boolean
}

interface AgentRunEventBase {
  /** 归属 run（§11 SSE 载荷统一含 run_id） */
  runId: string
  /** 严格递增序号，重连去重依据（§9.2） */
  sequence: number
  timestamp: string
}

export interface AgentRunStartedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.RUN_STARTED
  status: AgentRunStatus
  model?: string
  /** 本次 run 的预算上限（后端 run_started 载荷 budget） */
  budget?: AgentRunBudget
  /** 运行模式（INT-2474；缺省 chat） */
  mode?: AgentRunMode
  /** Auto 暂停策略（仅 Auto；启动前即可展示「何时会暂停」） */
  pausePolicy?: AgentRunPausePolicy
}

/** Auto 每轮进度（§9.4；当前步骤 / 预算水位 / 产物 / 续跑提示） */
export interface AgentAutoStepEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.AUTO_STEP
  progress: AgentAutoProgress
}

/** Auto 暂停（预算阈值 / 连续工具失败；run 转 WAITING_APPROVAL） */
export interface AgentRunPausedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.RUN_PAUSED
  pause: AgentAutoPause
}

/** 用户确认继续（记录暂停原因与预算确认，不产生正文） */
export interface AgentRunResumedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.RUN_RESUMED
  /** 被确认继续的暂停原因 */
  pauseReason?: AgentRunPauseReason
  /** 这次继续是否确认了预算暂停点（同一暂停点不再触发） */
  ackedBudgetPause?: boolean
  consecutiveFailures?: number
  budget?: AgentRunBudget
}

export interface AgentMessageDeltaEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.MESSAGE_DELTA
  /** 消息 id：重连回放时按 message_id + sequence 去重，不重复拼接（§11） */
  messageId: string
  delta: string
}

export interface AgentToolCallEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.TOOL_CALL
  toolCallId: string
  tool: string
  risk: AgentToolRisk
  /** 参数摘要（后端脱敏后摘要；前端只展示不执行） */
  summary?: string
}

export interface AgentToolResultEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.TOOL_RESULT
  toolCallId: string
  status: AgentToolResultStatus
  summary?: string
  /** 工具失败时的后端错误码（error_code；成功为空） */
  errorCode?: string
  sourceRefs?: AgentEventSourceRef[]
}

export interface AgentApprovalRequiredEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.APPROVAL_REQUIRED
  approvalId: string
  toolCallId?: string
  /** 工具名与风险等级（后端 approval_required 载荷 tool / risk） */
  tool?: string
  risk?: AgentToolRisk
  /** 过期时间（ISO；UI 本地倒计时，服务端 409 兜底） */
  expiresAt?: string
  /** 提案正文（approval_required 载荷 proposal，已由 DTO 转 camelCase） */
  proposal?: AgentApprovalProposal
  /**
   * §9.4.1 拆单批次：每张单一条 `approval_required`，同批 `toolCallId` 相同、
   * 共享 `batchId`，`batchIndex` 1..N。未拆单时字段缺省。
   * （object_ref 不在 SSE 载荷里，由随后刷新的审批列表补齐。）
   */
  batchId?: string
  batchIndex?: number
  batchTotal?: number
}

export interface AgentContextCompactedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.CONTEXT_COMPACTED
  /** 压缩层级（§8.2 L1_TRIM / L2_DEDUPE / L3_MEMO / L4_REBUILD） */
  level?: string
  snapshotVersion?: number
  tokenCountBefore?: number
  tokenCountAfter?: number
  droppedCount?: number
  /** 调试模式开关（AGENT_CONTEXT_DEBUG）；关闭时不下发被裁消息 */
  debug?: boolean
}

/**
 * 「把本次流程沉淀为 Skill」草案建议（§4.4 第 7 条第④项）。
 *
 * 后端只在 run 正常结束且实际调用 ≥2 个工具时下发；事件不落库
 * （`created=false`、`requires_confirmation=true`），用户确认后由会话页引导到
 * `/agent-skills` 新建 DRAFT，绝不自动创建或发布。
 */
export interface AgentSkillDraftSuggestedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.SKILL_DRAFT_SUGGESTED
  suggestedName: string
  description: string
  toolsUsed: string[]
  /** 本次 run 激活的 Skill（无则为空） */
  sourceSkill?: string
  /** 回执：事件不落库（服务端恒 false） */
  created: boolean
  requiresConfirmation: boolean
}

export interface AgentRunFinishedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.RUN_FINISHED
  status: AgentRunStatus
  error?: string
}

export interface AgentErrorEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.ERROR
  errorCode?: string
  errorMessage: string
  /**
   * 可恢复（上游中断，按 Last-Event-ID 续传即可，不是 run 终态）。
   * 网关在转发中断时合成 error 帧（agent_runtime_bp._sse_error_frame），其
   * `id` 取已下发水位，前端去重要允许「等于水位的可恢复帧」通过且不得关流。
   */
  recoverable?: boolean
}

/** 归一后的 SSE 事件（未识别类型由 DTO 层丢弃，避免把未知载荷当已知结构渲染） */
export type AgentRunEvent =
  | AgentRunStartedEvent
  | AgentMessageDeltaEvent
  | AgentToolCallEvent
  | AgentToolResultEvent
  | AgentApprovalRequiredEvent
  | AgentContextCompactedEvent
  | AgentSkillDraftSuggestedEvent
  | AgentAutoStepEvent
  | AgentRunPausedEvent
  | AgentRunResumedEvent
  | AgentRunFinishedEvent
  | AgentErrorEvent

/** 发起 run 的输入（POST /agent/sessions/{id}/runs） */
export interface AgentRunInput {
  /** 用户本轮消息正文（Auto 模式下即目标描述） */
  message: string
  /** 运行模式（缺省 chat；Auto 才带预算） */
  mode?: AgentRunMode
  /** 请求侧收紧预算（只能收紧，服务端取 min；0 / 负数视为不覆盖） */
  budget?: AgentRunBudget
}

/**
 * 网关总开关关闭的业务码（INT-2456 agent_guard.AGENT_DISABLED_CODE）。
 * 只有带此码的 503 才表示「功能未开启」，其余 503 是服务不可达。
 */
export const AGENT_DISABLED_CODE = 'AGENT_DISABLED'

/**
 * 网关合成的「上游中断」错误码（agent_runtime_bp._stream_events）：
 * 这两类不是 run 终态，按 Last-Event-ID 重连即可续传，前端不得判失败关流。
 */
export const AGENT_RECOVERABLE_ERROR_CODES: ReadonlySet<string> = new Set([
  'UPSTREAM_ERROR',
  'UPSTREAM_UNAVAILABLE',
])

export function isRecoverableAgentErrorCode(code: string | undefined): boolean {
  return code !== undefined && AGENT_RECOVERABLE_ERROR_CODES.has(code)
}

/**
 * Agent 通道错误文案（中文；§13 安全「Agent 总开关默认关闭，故障不影响人工流程」）。
 * 归 domain 而非 features：infrastructure 错误归一与页面文案共用同一口径，
 * 避免 infrastructure 反向依赖 features。
 */
export const AGENT_ERROR_COPY = {
  /** Agent 总开关关闭（网关 503 + code=AGENT_DISABLED） */
  disabled: '平台 Agent 当前未开启，请联系管理员开启后再试',
  /**
   * 服务不可达 / 未部署（503 但不是总开关：网关转发不到 agent_service、
   * 凭据主密钥不可用等）。不能报成「未开启」，否则把环境问题误导成配置问题。
   */
  serviceUnavailable: '平台 Agent 服务暂不可用，请稍后重试或切换到「自带供应商」通道',
  /** 会话 / run 不存在（404：run_id / session_id 无效或已被清理） */
  notFound: '会话或运行不存在，请重新开始对话',
  /** 无权限 / 会话失效 */
  unauthorized: '无权使用平台 Agent，请重新登录或联系管理员',
  network: '网络连接失败或服务无响应',
  /** 事件流重连次数耗尽 */
  streamFailed: 'Agent 事件流中断，请重试',
  /** run 终态 FAILED */
  runFailed: 'Agent 运行失败，请重试',
  /** run 终态 BUDGET_EXCEEDED */
  budgetExceeded: '本次运行超出预算已停止，请调整问题后重试',
  /** 终态 CANCELLED 徽标文案 */
  cancelled: '已取消',
  cancelFailed: '取消请求失败，请稍后重试',
  /** 空响应（run 既无事件也无终态） */
  emptyRun: 'Agent 未返回任何事件，请重试',
} as const

/**
 * Auto 模式文案（§9.4 / INT-2474；interface 层与 application 层共用，归 domain）。
 * 预算默认值只作「服务端默认」的说明文案（实际上限由服务端给定、请求只能收紧）。
 */
export const AGENT_AUTO_COPY = {
  /** 模式切换 */
  modeLabel: '运行模式',
  modeChat: '对话',
  modeChatHint: '单轮问答：一问一答，不自动多轮推进',
  modeAuto: 'Auto',
  modeAutoHint: '目标驱动：自动多轮推进，受预算约束，写操作仍需审批',
  autoBadge: 'Auto',
  /** 目标输入 */
  goalPlaceholder:
    '描述要让 Auto 完成的目标，例如：把标签为「回归测试」的用例全部跑一遍，再对比上次结果',
  /** 预算设置 */
  budgetTitle: 'Auto 预算',
  budgetHint: '只能收紧、不能放宽：留空即用服务端默认，超限会导致运行停止',
  budgetDefaultHint:
    '服务端默认（§9.4）：轮次 60 · 工具调用 120 · token 4×上下文窗口 · 时长 30 分钟 · 输出 20MB',
  /** 输入超过服务端默认时的口径提示（请求只能收紧；超限由服务端按上限执行） */
  budgetOverLimitHint: '超过服务端上限时按服务端上限执行',
  budgetRounds: '最大轮次',
  budgetToolCalls: '最大工具调用',
  budgetTokens: '最大 token（输入+输出）',
  budgetDuration: '最大时长',
  budgetOutput: '最大输出',
  unitRounds: '轮',
  unitToolCalls: '次',
  unitTokens: 'token',
  unitMinutes: '分钟',
  unitMegabytes: 'MB',
  budgetPlaceholderDefault: '默认',
  budgetInvalid: '请输入正整数，留空表示不收紧该项',
  budgetOpen: '设置预算',
  budgetClose: '收起预算',
  /** 暂停策略 */
  pausePolicy:
    '预算消耗到 80% 或连续 2 次工具失败时暂停，等你确认继续；DESTRUCTIVE 操作始终逐条审批',
  /** 进度面板 */
  progressTitle: 'Auto 进度',
  progressGoal: '目标',
  progressPlan: '当前计划',
  progressStep: '当前步骤',
  progressStepUnit: '步',
  progressBudget: '预算消耗',
  progressArtifacts: '已产出',
  progressArtifactCount: '个产物',
  progressNoArtifacts: '暂无产物',
  progressConsecutiveFailures: '连续失败',
  progressTimes: '次',
  progressInstruction: '已向模型回灌续跑提示',
  phasePendingResume: '已暂停，等待你确认继续',
  phaseResume: '已确认继续',
  phaseContinue: '续跑中',
  phaseStep: '执行中',
  /** 暂停 / 继续 / 结束 */
  pausedTitle: 'Auto 已暂停',
  pausedBudget: '预算已消耗到暂停阈值，请确认是否继续',
  pausedFailures: '连续 2 次工具失败，已暂停自动重试',
  pausedUnknown: 'Auto 已暂停，请确认是否继续',
  pausedUsage: '暂停时的预算水位',
  resume: '继续运行',
  resuming: '正在继续…',
  resumeFailed: '继续失败，请稍后重试',
  resumeNotPaused: '当前运行不处于暂停态，已刷新状态',
  resumeNeedsApproval: '仍有待审批提案，请先处理审批卡再继续',
  stop: '结束运行',
  stopping: '正在结束…',
  /** 终态 */
  finishedTitle: 'Auto 已完成',
  budgetExceededTitle: 'Auto 超出预算已停止',
  budgetExceededDesc: '已完成步骤与产物保留，调整目标或预算后可重新发起',
  circuitTitle: 'Auto 已熔断停止',
  circuitDesc: '连续工具失败达上限，不再自动重试；已完成产物保留',
  failedTitle: 'Auto 运行失败',
  failedDesc: '运行未能完成，请检查目标或稍后重试',
  cancelledTitle: 'Auto 已结束',
  /** 审批联动（Auto 下写操作仍逐条确认，不提供「全部自动批准」） */
  approvalsTitle: '待审批写操作',
  approvalsCount: '条待审批',
  approvalsHint: 'Auto 模式不预授权高危操作，须逐条确认',
  noBulkApprove: '不提供「全部自动批准」',
  /** 刷新恢复 */
  restoredPaused: 'Auto 运行处于暂停态（刷新前的进度不可回放），可继续或结束',
  restoreHint: '刷新后仅恢复暂停状态，进度时间线在本轮不可回放',
  /** 刷新恢复后点「继续」：本页不重接事件流，改按服务端快照跟随终态（P2） */
  restoredResuming: '已继续运行，正在等待服务端结果（刷新后的执行过程不在本页回放）',
  tracking: '已继续运行，正在等待服务端结果…（刷新后续跑不在本页回放步骤进度）',
  trackingFailed: '暂时无法获取运行结果，请刷新页面查看',
  trackingTimeout: '等待运行结果超时，请刷新页面查看',
  /** 请求失败 */
  sendFailed: 'Auto 任务发起失败，请稍后重试',
  loadFailed: 'Auto 状态加载失败',
} as const

/** Auto 模式目标输入最小长度（后端 message min_length=1，空串不派发） */
export const AUTO_GOAL_MIN_LENGTH = 1

/** Auto 终态判定所需的错误码（后端 run_finished.error / 熔断原因） */
export const AGENT_AUTO_ERROR_CODE = {
  CONSECUTIVE_TOOL_FAILURES: 'CONSECUTIVE_TOOL_FAILURES',
} as const

/**
 * 审批卡文案（§9.4 / §12.2；application 的决策错误归一与 features 的卡片共用，
 * 归 domain 避免 application 反向依赖 features）。
 */
export const AGENT_APPROVAL_COPY = {
  title: '写操作审批',
  planTitle: '本步骤写操作',
  pending: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  expired: '已过期',
  approve: '批准执行',
  reject: '拒绝',
  approving: '正在批准…',
  rejecting: '正在拒绝…',
  /** 决策成功后服务端继续执行写操作（决策本身不执行业务写） */
  approvedHint: '已批准，Agent 将在服务端执行该写操作',
  rejectedHint: '已拒绝，该写操作不会执行',
  expiredHint: '提案已过期，写操作未执行且不可再批准',
  /**
   * 刷新恢复：run 服务端仍在等审批时，被打断的 assistant 气泡按「等待审批」中性收口
   * （不再落事件流中断错误态）；气泡无正文时用这句兜底。
   */
  waitingMessage: '已生成写操作提案，请在下方的审批卡中批准或拒绝',
  /** 过期倒计时前缀（剩余 mm:ss） */
  expiresIn: '剩余',
  expiresAt: '有效期至',
  decidedBy: '决策人',
  decidedAt: '决策时间',
  arguments: '参数（已脱敏）',
  diff: '变更预览',
  diffRequest: '将发起的请求',
  /** 本步骤其余写操作的折叠标题 */
  moreInStep: '本步骤其余写操作',
  /** 决策失败文案 */
  conflict: '审批已失效或已被处理，已刷新最新状态',
  notFound: '审批单不存在或无权访问',
  decisionFailed: '审批请求失败，请稍后重试',
  loadFailed: '待审批状态加载失败',
  loading: '正在同步审批状态…',
  retry: '重试',
  empty: '当前没有待审批的写操作',
  /** 计数徽标（与工具卡计数同源） */
  pendingCount: '待审批',
  toolCallCount: '工具调用',
  /** 破坏性操作二次确认（INT-2467 契约：批准必须带 confirm=true） */
  destructiveConfirmTitle: '确认执行高危操作？',
  destructiveConfirmDesc:
    '该操作不可回滚（重启 / 关机 / 安装 / 卸载 / 批量设备控制等）。确认后服务端才会执行。',
  /** 单次影响对象数超过上限（§9.4 >20 对象必须逐条审批） */
  batchObjects: '影响对象',
  batchConfirmTitle: '批量写操作超过单次审批上限',
  batchConfirmDesc:
    '本次提案影响的对象数超过 20 个（§9.4）。必须逐项核对后才能批准；不允许一次批量放行。',
  batchConfirmPrefix: '本次提案影响',
  batchConfirmSuffix: '个对象，超过单次审批上限（20 个）',
  /** 卡片行内提示（不依赖前缀计数，单独成句） */
  batchLimitHint: '影响对象超过单次审批上限（20 个），须逐项核对后批准',
  batchObjectToggled: '已核对',
  batchObjectCount: '已核对',
  batchConfirmApprove: '逐项核对后批准',
  /** 二次确认动作与补确认提示 */
  confirmApprove: '确认批准',
  confirmTitle: '二次确认',
  unknownRiskConfirmDesc:
    '该操作的风险等级未知，按高危处理，需要二次确认后才能批准。',
  confirmRequired: '该操作需要二次确认，请核对后重新批准',
  /**
   * §9.4.1 拆单批次：一次 tool call 影响 >20 对象时拆成 N 张单，
   * 决策逐张、执行 all-or-nothing（本批全部批准后才用完整参数执行一次）。
   */
  batchGroupPrefix: '本批',
  batchGroupUnit: '张单',
  batchObjectPrefix: '对象',
  batchObjectUnit: '个',
  /** 单卡序号徽标：本批第 i/N 条 */
  batchIndexPrefix: '本批第',
  batchIndexSuffix: '条',
  /** 单卡行内提示：本批全部批准后才执行 */
  batchPendingHint: '本批全部批准后才执行',
  /** 组头状态口径 */
  batchAllPending: '本批全部批准后才执行',
  batchAllApproved: '本批已全部批准，待执行',
  batchRejected: '本批不执行（任一单被拒绝）',
  batchExpired: '本批不执行（任一单已过期）',
  /** 单卡对象摘要前缀（object_ref.kind + ids） */
  batchObjectRef: '本单对象',
  /** 非枚举范围（object_ref.ids 为空，影响面由服务端决定） */
  batchObjectRange: '按范围执行',
} as const
