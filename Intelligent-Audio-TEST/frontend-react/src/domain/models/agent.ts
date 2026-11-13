/**
 * Agent 会话 / Run / 事件领域模型（domain 层；doc/agent化/07_单Agent_Skills落地方案.md
 * §5.3 枚举、§9.1 状态机、§9.2 断点续跑、§11 API 与 SSE）。
 *
 * 架构红线：domain 只见 camelCase 领域对象；后端 snake_case 契约的转换只发生在
 * infrastructure/dto/agent.dto.ts。枚举一律常量化（禁止魔法字符串）。
 */

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

/** 待审批提案（§10 agent_approval；M2 审批卡实现，本卡只接空列表契约） */
export interface AgentApproval {
  id: string
  runId: string
  toolCallId?: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED'
  proposal?: unknown
  diff?: unknown
  expiresAt?: string
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
  proposal?: unknown
}

export interface AgentContextCompactedEvent extends AgentRunEventBase {
  type: typeof AGENT_EVENT_TYPE.CONTEXT_COMPACTED
  /** 压缩层级（§8.2 L1_TRIM / L2_DEDUPE / L3_MEMO / L4_REBUILD） */
  level?: string
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
