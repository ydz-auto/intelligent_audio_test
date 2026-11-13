/**
 * 模型供应商页文案与常量（features/agent-providers）。
 * 文案全中文；页面只通过本文件取文案，避免散落魔法字符串。
 */
import { AGENT_PROVIDER_PROTOCOL, type AgentProviderProtocol } from '@/domain/models/agentProvider'

/** 页面路由（入口按钮 / 无 Key 引导共用） */
export const AGENT_PROVIDERS_ROUTE = '/agent-providers' as const

/** 管理权限码（路由守卫 / 导航 / 入口按钮同一集合） */
export const AGENT_PROVIDER_MANAGE_PERMISSION = 'agent:provider:manage' as const

export const AGENT_PROVIDERS_COPY = {
  pageTitle: '模型供应商',
  pageDescription:
    '配置平台 Agent 使用的模型供应商（用户自带 Key）。密钥加密保存，页面只显示掩码，任何日志与截图都不会出现明文。',
  securityNotice:
    '协议支持 OpenAI 兼容与 Anthropic；Key 以 AES-256-GCM 加密落库，编辑时留空表示不修改。',

  listTitle: '我的供应商',
  listDescription: '默认供应商用于所有新的 Agent 会话。',
  loading: '正在加载模型供应商…',
  loadErrorTitle: '模型供应商加载失败',
  retry: '重新加载',
  emptyTitle: '还没有配置模型供应商',
  emptyDescription: '添加一个供应商后，平台 Agent 才能调用模型；也可以稍后在会话页的引导里配置。',

  addButton: '新增供应商',
  addTitle: '新增模型供应商',
  addDescription: '密钥只在提交时传输一次，保存后仅显示掩码。',
  editTitle: '编辑模型供应商',
  editDescription: 'API Key 留空表示不修改原密钥；页面不会回显明文。',

  fieldName: '名称',
  fieldNamePlaceholder: '如：DeepSeek 主力（留空取模型名）',
  fieldProtocol: '协议',
  fieldBaseUrl: 'Base URL',
  fieldBaseUrlPlaceholder: 'https://api.deepseek.com/v1',
  fieldModel: '模型名',
  fieldModelPlaceholder: '如：deepseek-chat',
  fieldApiKey: 'API Key',
  fieldApiKeyPlaceholderCreate: 'sk-...',
  fieldApiKeyPlaceholderEdit: '留空表示不修改，例如 sk-...',
  fieldApiKeyHint: '密钥加密保存；保存后仅显示 sk-****abcd 掩码，不会回显明文。',
  showKey: '显示密钥',
  hideKey: '隐藏密钥',

  fieldContextWindow: '上下文窗口',
  contextModeDefault: '使用默认',
  contextModeOverride: '手动覆盖',
  contextReset: '恢复默认',
  contextCatalogHint: '目录默认',
  contextMaxOutputHint: '最大输出',
  contextFallbackHint: '128k 兜底',
  contextInputHint: '范围 8k–2M，按 1024 对齐；单位：tokens',
  contextAboveCatalogWarning: '覆盖值高于目录默认，仍会保存，预算按覆盖值计算。',
  contextSourceHint: '保存后显示的来源',
  contextInvalid: '请填写合法的上下文窗口',

  invalidBaseUrl: 'Base URL 必须是 http(s) 地址',
  invalidModel: '请填写模型名',
  invalidApiKey: '请填写 API Key',
  invalidApiKeyTooLong: 'API Key 不能超过 512 字符',
  invalidBaseUrlTooLong: 'Base URL 不能超过 500 字符',

  save: '保存',
  saving: '保存中…',
  cancel: '取消',

  defaultBadge: '默认',
  setDefault: '设为默认',
  setDefaultAria: (name: string) => `将 ${name} 设为默认`,
  verify: '验证连通性',
  verifying: '验证中…',
  verifyAria: (name: string) => `验证 ${name} 的连通性`,
  edit: '编辑',
  editAria: (name: string) => `编辑 ${name}`,
  delete: '删除',
  deleteAria: (name: string) => `删除 ${name}`,
  deleteTitle: '删除模型供应商？',
  deleteDescription:
    '删除后该供应商的密钥密文将被清空且不可恢复；若它是默认项，系统会自动把最早可用的供应商设为默认。',

  effectiveWindow: '有效窗口',
  sourceLabel: '来源',
  lastVerified: '最近验证',
  notVerified: '未验证',
  keyMissing: '密钥缺失',
  protocolLabel: '协议',
  createdAt: '创建时间',

  guidanceTitle: '未配置模型供应商',
  guidanceDescription:
    '平台 Agent 需要你自己的模型 Key 才能运行（平台不提供默认 Key）。请先添加一个供应商并设为默认。',
  guidanceAction: '去配置模型供应商',

  sessionSummaryPrefix: '平台模型',
  sessionNoProvider: '未配置模型供应商',
  sessionGoConfigure: '去配置',
} as const

/** 协议下拉选项（label 供 Select 的 items 使用，避免回显原始 value） */
export const AGENT_PROVIDER_PROTOCOL_SELECT_ITEMS: ReadonlyArray<{
  value: AgentProviderProtocol
  label: string
}> = [
  {
    value: AGENT_PROVIDER_PROTOCOL.OPENAI_COMPATIBLE,
    label: 'OpenAI 兼容（DeepSeek / Qwen / 自建网关）',
  },
  {
    value: AGENT_PROVIDER_PROTOCOL.ANTHROPIC,
    label: 'Anthropic',
  },
]

/** 上下文档位模式 */
export const CONTEXT_WINDOW_MODE = {
  DEFAULT: 'default',
  OVERRIDE: 'override',
} as const

export type ContextWindowMode =
  (typeof CONTEXT_WINDOW_MODE)[keyof typeof CONTEXT_WINDOW_MODE]
