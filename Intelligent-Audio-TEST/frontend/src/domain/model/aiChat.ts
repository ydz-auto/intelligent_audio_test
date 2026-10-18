/**
 * 灵犀Agent AI 对话领域模型（domain 层；08_AI对话页.md §7 落位）。
 * 形态对照 React 08_AI对话页（INT-415）domain/models/aiChat.ts 平移，
 * Agent 会话契约（§3.8）占位——后端 F6（DeepSeek Harness）待立项，
 * 数据交互面全部标「待后端立项」，不做假数据兜底。
 */

/** 消息角色 */
export type ChatMessageRole = 'user' | 'assistant' | 'system'

/** 消息状态（loading/streaming/complete/error） */
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

/** 文档变更卡（studio_apply_edit / studio_restore_version 成功后嵌入，§3.4；待后端立项） */
export interface ChatDocumentChange {
  documentId: string
  documentName: string
  version: number
  changes: Array<{ action: '新增' | '删除' | '修改'; section: string }>
}

/** 思考过程（DSH 推理事件待后端立项，版式先行） */
export interface ChatReasoning {
  content: string
  duration: number
}

/** 对话消息 */
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

/**
 * 报告上下文类型：
 * - task/comparison/secondary_comparison 对照 ReportType 枚举（报告数据源 GET /reports 的 type 字段）；
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
 * 能力 → 权限码映射（08_AI对话页 §5 表单一来源，对齐 seed_rbac.py 实测；
 * report:update 为过渡口径，Studio 专码 report:studio:* 待后端立项后替换）。
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

/** 全局 Agent 工作台浮窗开关存储键（§3.1B：跨页面刷新/路由保持） */
export const AGENT_WORKBENCH_STORAGE_KEY = 'iatp:agent-workbench:v1'
