/**
 * AI 对话页常量（interfaces 层；08_AI对话页.md §6 中文文案全量 + §3.3/§3.4/§3.5 注册表）。
 */
import { FileBarChart, GitCompareArrows, BarChart3, MessageCircleQuestion } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type {
  ChatConfig,
  ChatParameterEnabled,
  ChatParameterKey,
} from '@/domain/models/aiChat'
import { AGENT_CAPABILITY_PERMISSIONS, AI_CHAT_STORAGE_KEYS } from '@/domain/models/aiChat'

export { AI_CHAT_STORAGE_KEYS as STORAGE_KEYS }

export const MESSAGE_ROLES = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
} as const

export const MESSAGE_STATUS = {
  LOADING: 'loading',
  STREAMING: 'streaming',
  COMPLETE: 'complete',
  ERROR: 'error',
} as const

export const MAX_RENDERED_HISTORY_MESSAGES = 24

/** 生成参数默认值（§3.5 注册表，照 newAPI DEFAULT_CONFIG 全值） */
export const DEFAULT_CONFIG: ChatConfig = {
  temperature: 0.7,
  top_p: 1,
  max_tokens: 4096,
  frequency_penalty: 0,
  presence_penalty: 0,
  seed: null,
}

/** 参数默认启用态（照 newAPI DEFAULT_PARAMETER_ENABLED） */
export const DEFAULT_PARAMETER_ENABLED: ChatParameterEnabled = {
  temperature: true,
  top_p: true,
  max_tokens: false,
  frequency_penalty: true,
  presence_penalty: true,
  seed: false,
}

/** 六参数注册表（§3.5 表；label/description 中文文案 §6） */
export type AgentParameterControl = {
  key: ChatParameterKey
  label: string
  description: string
  valueType: 'slider' | 'number'
  min: number
  max: number
  step: number
}

export const AGENT_PARAMETER_CONTROLS: readonly AgentParameterControl[] = [
  {
    key: 'temperature',
    label: '温度',
    description: '控制输出的随机性和创造性',
    valueType: 'slider',
    min: 0.1,
    max: 1,
    step: 0.1,
  },
  {
    key: 'top_p',
    label: 'Top P',
    description: '按概率质量限制词元选择范围',
    valueType: 'slider',
    min: 0.1,
    max: 1,
    step: 0.1,
  },
  {
    key: 'frequency_penalty',
    label: '频率惩罚',
    description: '减少重复措辞',
    valueType: 'slider',
    min: -2,
    max: 2,
    step: 0.1,
  },
  {
    key: 'presence_penalty',
    label: '存在惩罚',
    description: '鼓励讨论新话题',
    valueType: 'slider',
    min: -2,
    max: 2,
    step: 0.1,
  },
  {
    key: 'max_tokens',
    label: '最大 Tokens',
    description: '限制回复长度',
    valueType: 'number',
    min: 0,
    max: 200000,
    step: 1,
  },
  {
    key: 'seed',
    label: '随机种子',
    description: '让兼容模型的回复更可复现',
    valueType: 'number',
    min: 0,
    max: 2147483647,
    step: 1,
  },
] as const satisfies readonly AgentParameterControl[]

/** 空态四 starter（§3.3 表；权限过滤，隐藏而非置灰） */
export type StarterPrompt = {
  key: string
  label: string
  icon: LucideIcon
  prompt: string
  requiredPermission: string | null
}

export const STARTER_PROMPTS: StarterPrompt[] = [
  {
    key: 'generate',
    label: '生成测试报告',
    icon: FileBarChart,
    prompt: '帮我把最近的测试任务生成一份测试报告',
    requiredPermission: AGENT_CAPABILITY_PERMISSIONS.generate,
  },
  {
    key: 'compare',
    label: '对比多份报告',
    icon: GitCompareArrows,
    prompt: '对比最近两次测试的报告，找出差异和退步项',
    requiredPermission: AGENT_CAPABILITY_PERMISSIONS.compare,
  },
  {
    key: 'analyze',
    label: '解读报告指标',
    icon: BarChart3,
    prompt: '解读这份报告的核心指标，指出异常项',
    requiredPermission: AGENT_CAPABILITY_PERMISSIONS.read,
  },
  {
    key: 'ask',
    label: '追问报告数据',
    icon: MessageCircleQuestion,
    prompt: '这次测试的通过率是多少？和上一版比怎么样？',
    requiredPermission: AGENT_CAPABILITY_PERMISSIONS.read,
  },
]

/** DSH 工具中文显示名映射（§3.4 表；待后端立项） */
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

export const AGENT_TOOL_STATUS_LABELS = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  error: '失败',
} as const

/** 消息操作文案（§6） */
export const MESSAGE_ACTION_LABELS = {
  copy: '复制',
  copied: '已复制',
  regenerate: '重新生成',
  showSource: '显示源码',
  showPreview: '显示预览',
  edit: '编辑',
  delete: '删除',
  undo: '撤销修改',
  retry: '重试',
  openMenu: '打开菜单',
  noContent: '没有可复制的内容',
  waitGeneration: '请等待当前回复生成完成',
  viewDocument: '查看文档',
} as const

/** 错误文案（§6） */
export const ERROR_MESSAGES = {
  title: '出错了',
  retry: '重试',
  editAndResend: '编辑后重发',
  generic: 'AI 助手暂时无法处理，请重试',
  network: '网络连接失败或服务无响应',
  fallback: 'AI 助手暂时不可用，您仍可在报告中心查看标准报告',
  interrupted: '生成已中断',
} as const

/** 空态文案（§6） */
export const EMPTY_STATE_COPY = {
  title: '开始与 AI 助手对话',
  description:
    'AI 基于报告数据起草文档、对比结果、解读指标——所有数值均来自报告七表，AI 只起草不算数。',
  placeholder: '描述你的报告需求，例如：帮我把任务 #320 的测试结果生成一份报告',
  loading: '正在加载对话...',
} as const
