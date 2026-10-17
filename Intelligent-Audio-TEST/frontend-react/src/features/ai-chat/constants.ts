/**
 * AI 对话页常量（interfaces 层；08_AI对话页.md §6 中文文案全量 + §3.3/§3.5/§3.11）。
 * 2026-10-17 新口径：模型参数六项注册表整块移除（无参数面板），仅保留模型/供应商切换。
 */
import { FileBarChart, GitCompareArrows, BarChart3, MessageCircleQuestion } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { ChatConfig } from '@/domain/models/aiChat'
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

/** 会话配置默认值（§3.5/§3.11：模型/供应商选择；无模型参数） */
export const DEFAULT_CONFIG: ChatConfig = {
  providerId: undefined,
  modelId: undefined,
}

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

/** 空态文案（§6；Demo 说明尾注 §3.10——上线为 Demo 预览版，Agent 报告能力接入后完整开放） */
export const EMPTY_STATE_COPY = {
  title: '开始与灵犀Agent对话',
  description:
    '灵犀Agent基于报告数据起草文档、对比结果、解读指标——所有数值均来自报告七表，AI 只起草不算数。当前为 Demo 预览，Agent 报告能力接入后完整开放。',
  placeholder: '描述你的报告需求，例如：帮我把任务 #320 的测试结果生成一份报告',
  loading: '正在加载对话...',
} as const

/** Demo 标注文案（§3.10；顶部条/全局浮窗头行） */
export const DEMO_COPY = {
  badge: 'Demo',
  tooltip: '演示版：Agent 能力待接入，对话使用你配置的 LLM 供应商',
  floatingTooltip: '演示版，未接入实际后端',
} as const

/** 模型/供应商切换器文案（§3.5/§6） */
export const MODEL_PROVIDER_COPY = {
  selectModel: '选择模型',
  selectProvider: '选择供应商',
  noProvider: '未配置 LLM 供应商 → 点击配置',
  manageProviders: '管理供应商',
} as const

/** 供应商管理弹窗文案（§3.11/§6） */
export const PROVIDER_MANAGER_COPY = {
  title: 'LLM 供应商管理',
  description: '配置你自己的 AI 对话连接：填写供应商名称、API 地址与密钥。密钥仅保存在本机。',
  addProvider: '添加供应商',
  name: '名称',
  baseUrl: 'API Base URL',
  apiKey: 'API Key',
  showHide: '显示/隐藏',
  modelList: '模型列表',
  fetchModels: '自动获取模型列表',
  testConnection: '测试连接',
  setDefault: '设为默认',
  default: '默认',
  keyConfigured: '已配置 Key',
  keyMissing: '未配置 Key',
  save: '保存',
  delete: '删除',
  edit: '编辑',
  cancel: '取消',
  testSuccess: '连接成功 · {n} 个模型',
  testFail: '无法连接该供应商',
  fetchSuccess: '已获取 {n} 个模型',
  deleteTitle: '删除供应商？',
  deleteDesc: '该供应商的密钥将从本机移除，确定继续？',
  footerHint: 'Demo 预览：供应商仅存本机，不上传平台；切换模型/供应商后新对话生效。',
  baseUrlPlaceholder: 'https://api.openai.com/v1',
  addEditTitle: '添加供应商',
  editTitle: '编辑供应商',
} as const
