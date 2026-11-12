/**
 * AI 对话页领域模型（domain 层；08_AI对话页.md §7）。
 * 形态对照 api_gateway/schemas/report.py + task.py（ReportListItem/TaskListItem）与
 * Agent 会话契约占位（§3.8，待后端立项）；mock 数据与真实 schema 对齐，后续接线字段不返工。
 */
import type { AgentRunStatus } from './agent'

export type ChatMessageRole = 'user' | 'assistant' | 'system'

export type ChatMessageStatus = 'loading' | 'streaming' | 'complete' | 'error'

/**
 * 对话通道（INT-2457 M0）：
 * - platform：走平台 Agent（agent_service 会话 / Run / SSE，默认）；
 * - provider：自带 LLM 供应商直连（降级模式；P0-1 拍板后二选一，不长期双轨）。
 */
export const CHAT_CHANNEL = {
  PLATFORM: 'platform',
  PROVIDER: 'provider',
} as const

export type ChatChannel = (typeof CHAT_CHANNEL)[keyof typeof CHAT_CHANNEL]

export function normalizeChatChannel(value: unknown): ChatChannel {
  return value === CHAT_CHANNEL.PROVIDER ? CHAT_CHANNEL.PROVIDER : CHAT_CHANNEL.PLATFORM
}

/** 消息版本（编辑器保存产生新版本；照 newAPI MessageVersion） */
export interface ChatMessageVersion {
  id: string
  content: string
}

/** 数据来源 sourceRef（报告七表：报告 ID + 指标 ID + 数据版本；无法证明来源 → verified=false） */
export interface ChatSourceRef {
  reportId: number
  metricId?: string
  dataVersion?: string
  verified?: boolean
}

/** DSH Agent 工具调用卡（§3.4 工具执行卡；待后端立项） */
export type AgentToolStatus = 'pending' | 'running' | 'completed' | 'error'

export interface AgentToolCall {
  id: string
  /** DSH 工具键（report_get_facts / studio_create_draft / compare_reports ...） */
  tool: string
  label: string
  status: AgentToolStatus
  summary?: string
  /** 工具失败时的后端错误码（tool_result.error_code） */
  errorCode?: string
  sourceRefs?: ChatSourceRef[]
}

/** 文档变更卡（studio_apply_edit / studio_restore_version 成功后嵌入，§3.4） */
export interface ChatDocumentChange {
  documentId: string
  documentName: string
  version: number
  changes: Array<{ action: '新增' | '删除' | '修改'; section: string }>
}

export interface ChatReasoning {
  content: string
  duration: number
}

export interface ChatMessage {
  key: string
  from: ChatMessageRole
  versions: ChatMessageVersion[]
  createdAt?: number
  startedAt?: number
  completedAt?: number
  durationMs?: number
  status?: ChatMessageStatus
  errorCode?: string | null
  reasoning?: ChatReasoning
  isReasoningStreaming?: boolean
  toolCalls?: AgentToolCall[]
  documentChanges?: ChatDocumentChange[]
  sourceRefs?: ChatSourceRef[]
  /**
   * 平台 Agent 通道的 run 终态（INT-2457）：CANCELLED / FAILED / BUDGET_EXCEEDED
   * 在消息尾部显示状态徽标；成功完成不显示。
   */
  runStatus?: AgentRunStatus
}

/**
 * 报告上下文类型：
 * - task/comparison/secondary_comparison 对照 ReportType 枚举（shared/models/common_enums.py 实测，
 *   报告数据源 GET /reports 的 type 字段）；
 * - task_context = GET /tasks 任务上下文（非报告，无 ReportType；「生成报告」入口语义）。
 */
export type ReportContextType =
  | 'task'
  | 'comparison'
  | 'secondary_comparison'
  | 'task_context'

export interface ReportContextOption {
  id: string
  label: string
  type: ReportContextType
  badge: string
  description?: string
}

/**
 * 会话配置（2026-10-17 负责人口径：模型参数六项注册表整块移除，仅保留模型/供应商切换）。
 * config 含模型/供应商选择（§3.5/§3.11）与报告上下文 id（§3.7 URL 契约）；
 * 报告上下文选择器 Demo 态整块不渲染（§3.5/§3.10），字段保留供立项后接线。
 */
export interface ChatConfig {
  /** 当前 LLM 供应商 id（用户自管，§3.11；localStorage iatp:ai-chat:v1:providers） */
  providerId?: string
  /** 当前模型 id（供应商可用模型列表内） */
  modelId?: string
  /**
   * 对话通道（INT-2457）：platform=平台 Agent（默认，配置决定）；provider=自带供应商直连。
   * 缺省按 platform 处理（normalizeChatChannel）。
   */
  chatMode?: ChatChannel
  reportContextId?: string
  reportContextLabel?: string
  reportContextType?: ReportContextType
}

/**
 * LLM API 供应商（§3.11 用户自管，chatbox 式；Demo 态存 localStorage 明文，
 * 不上传平台后端；正式版密钥管理待后端立项）。
 */
export interface LlmProvider {
  id: string
  name: string
  baseUrl: string
  /** 密钥仅存用户本地；Demo 态 localStorage 明文（§3.11 安全注记） */
  apiKey: string
  /** 该供应商可用模型 id 列表（用户手动登记或自动拉取） */
  models: string[]
  /** 默认供应商标记；默认=首个添加（§3.11 行为） */
  isDefault?: boolean
}

/**
 * 能力 → 权限码映射（§5 表单一来源，对齐 seed_rbac.py 实测；report:update 为过渡口径，
 * Studio 专码 report:studio:* 待后端立项后替换）。
 */
export const AGENT_CAPABILITY_PERMISSIONS = {
  generate: 'report:create',
  compare: 'report:compare',
  read: 'report:read',
  update: 'report:update',
} as const

/** 会话持久化键名（§3.7 照 playground 三键，命名空间 iatp:ai-chat:v1；
 * 2026-10-17 新口径：parameter-enabled 键废弃——无模型参数设置） */
export const AI_CHAT_STORAGE_KEYS = {
  config: 'iatp:ai-chat:v1:config',
  messages: 'iatp:ai-chat:v1:messages',
  providers: 'iatp:ai-chat:v1:providers',
} as const
