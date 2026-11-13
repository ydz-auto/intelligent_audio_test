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
}

/** 待审批提案（§10 agent_approval；M2 审批卡实现） */
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
}

/** Run 预算（§9.3/§9.4；后端 agent_run.budget，字段名与配置一致） */
export interface AgentRunBudget {
  maxRounds?: number
  maxToolCalls?: number
  maxTokens?: number
  maxDurationSeconds?: number
  maxOutputBytes?: number
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
  | AgentRunFinishedEvent
  | AgentErrorEvent

/** 发起 run 的输入（POST /agent/sessions/{id}/runs） */
export interface AgentRunInput {
  /** 用户本轮消息正文 */
  message: string
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
} as const
