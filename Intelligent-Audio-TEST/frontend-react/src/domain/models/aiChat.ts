/**
 * AI 对话页领域模型（domain 层；08_AI对话页.md §7）。
 * 形态对照 api_gateway/schemas/report.py + task.py（ReportListItem/TaskListItem）与
 * Agent 会话契约占位（§3.8，待后端立项）；mock 数据与真实 schema 对齐，后续接线字段不返工。
 */

export type ChatMessageRole = 'user' | 'assistant' | 'system'

export type ChatMessageStatus = 'loading' | 'streaming' | 'complete' | 'error'

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
}

/** 报告上下文类型（对照 ReportListItem.type：test-report/compare-report/secondary-compare + 任务） */
export type ReportContextType =
  | 'test-report'
  | 'compare-report'
  | 'secondary-compare'
  | 'task'

export interface ReportContextOption {
  id: string
  label: string
  type: ReportContextType
  badge: string
  description?: string
}

/** 生成参数配置（六参数，§3.5 注册表） */
export interface ChatConfig {
  temperature: number
  top_p: number
  max_tokens: number
  frequency_penalty: number
  presence_penalty: number
  seed: number | null
  reportContextId?: string
  reportContextLabel?: string
  reportContextType?: ReportContextType
}

export type ChatParameterKey =
  | 'temperature'
  | 'top_p'
  | 'max_tokens'
  | 'frequency_penalty'
  | 'presence_penalty'
  | 'seed'

export type ChatParameterEnabled = Record<ChatParameterKey, boolean>

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

/** 会话持久化键名（§3.7 照 playground 三键，命名空间 iatp:ai-chat:v1） */
export const AI_CHAT_STORAGE_KEYS = {
  config: 'iatp:ai-chat:v1:config',
  messages: 'iatp:ai-chat:v1:messages',
  parameterEnabled: 'iatp:ai-chat:v1:parameter-enabled',
} as const
