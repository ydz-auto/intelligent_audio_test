/**
 * AI 对话页常量（interfaces 层；08_AI对话页.md §6 中文文案全量 + §3.3/§3.5/§3.11）。
 * 2026-10-17 新口径：模型参数六项注册表整块移除（无参数面板），仅保留模型/供应商切换；
 * 2026-10-17 08:06 负责人口径：灵犀Agent 主工作台主推全部能力（61 工具 / 11 域），
 * 空态 starter 升级为「常用入门（报告四卡）+ 全能力分组（11 域）」。
 */
import {
  Activity,
  AudioWaveform,
  BarChart3,
  Box,
  ClipboardList,
  FileBarChart,
  FileText,
  Gauge,
  GitCompareArrows,
  Headphones,
  ListChecks,
  MessageCircleQuestion,
  Music,
  Settings,
} from 'lucide-react'
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

/** 空态四 starter（§3.3 区一「常用入门」表；权限过滤，隐藏而非置灰） */
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

/**
 * 全能力分组入口（§3.3 区二「全能力分组」：11 域，61 工具按 doc/agent化/01_功能介绍.md
 * §2.1/§2.2 分域归并，不杜撰能力名；域图标复用该域业务页/侧栏既有图标语义。
 * 2026-10-17 08:06 负责人口径：灵犀Agent 主工作台主推全部能力、不只报告三件）。
 */
export type CapabilityGroup = {
  /** 分组键（路由域，唯一） */
  key: string
  /** 分组名（路由域，中文；§3.3 表左列） */
  label: string
  /** 域能力名（01_功能介绍.md §2.2，中文） */
  domainLabel: string
  /** 工具数（§2.2 实测；null=配置域不在 61 工具清单，Agent 化待后端立项） */
  toolCount: number | null
  /** 图标（复用侧栏/业务页既有图标语义，§3.3） */
  icon: LucideIcon
  /** 在册权限码（命中即显可执行；null=无码域统一标「待接入」） */
  requiredPermission: string | null
  /** 示例快捷指令（点击回填输入框、不自动发送；null=待后端立项占位） */
  prompt: string | null
}

export const CAPABILITY_GROUPS: CapabilityGroup[] = [
  {
    key: 'dashboard',
    label: '工作台',
    domainLabel: '系统概览',
    toolCount: 2,
    icon: Activity,
    requiredPermission: 'home:read',
    prompt: '当前平台的用例、任务、设备、音频统计是多少？',
  },
  {
    key: 'audio',
    label: '音频导入',
    domainLabel: '音频导入+标注',
    toolCount: 5,
    icon: Music,
    requiredPermission: 'audio:read',
    prompt: '帮我从 URL 导入这批音频并带上标注',
  },
  {
    key: 'testcase',
    label: '用例管理',
    domainLabel: '用例生成/编辑+标签',
    toolCount: 14,
    icon: ListChecks,
    requiredPermission: 'testcase:read',
    prompt: '按标注内容分场景生成测试用例并打标签',
  },
  {
    key: 'evaluation',
    label: '评估维度',
    domainLabel: '评估维度配置',
    toolCount: 5,
    icon: Gauge,
    requiredPermission: 'evaluation:read',
    prompt: '列出评估维度，帮我新增一个评分维度',
  },
  {
    key: 'algorithm',
    label: '算法配置',
    domainLabel: '算法配置管理',
    toolCount: 5,
    icon: Box,
    requiredPermission: 'algorithm:read',
    prompt: '列出算法定义并配置参考参数',
  },
  {
    key: 'task',
    label: '任务域',
    domainLabel: '任务执行+控制',
    toolCount: 7,
    icon: ClipboardList,
    requiredPermission: 'task:read',
    prompt: '把上次失败的任务重跑一下',
  },
  {
    key: 'spl',
    label: 'SPL 校准',
    domainLabel: '声压级校准',
    toolCount: 4,
    icon: AudioWaveform,
    requiredPermission: 'spl:read',
    prompt: '执行一次 SPL 校准并查看历史',
  },
  {
    key: 'device',
    label: '设备',
    domainLabel: '播放设备管理+设备驱动生成',
    toolCount: 6,
    icon: Headphones,
    requiredPermission: 'device:read',
    prompt: '扫描播放设备，为豆包 APP 生成 Android 驱动',
  },
  {
    key: 'log',
    label: '日志诊断',
    domainLabel: '日志诊断',
    toolCount: 4,
    icon: FileText,
    requiredPermission: 'log:read',
    prompt: '这个任务为什么失败，帮我查日志诊断',
  },
  {
    key: 'report',
    label: '报告域',
    domainLabel: '结果分析+报告+报告对比',
    toolCount: 9,
    icon: FileBarChart,
    requiredPermission: 'report:read',
    prompt: '对比最近两次测试的报告，找出退步项',
  },
  {
    key: 'system-settings',
    label: '系统设置',
    domainLabel: '配置域（OAuth/系统配置）',
    toolCount: null,
    icon: Settings,
    requiredPermission: null,
    prompt: null,
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
  /** 2026-10-17 审计返修（P1）：对话由用户自配 LLM 供应商驱动（§3.11），无供应商/无模型时语义化引导 */
  noProviderChat: '未配置 LLM 供应商，请先在「管理供应商」中添加',
  noModel: '请先在模型/供应商切换器中选择模型',
} as const

/** 空态文案（§6；Demo 说明尾注 §3.10——上线为 Demo 预览版，Agent 能力接入后完整开放；
 * 2026-10-17 08:06 负责人口径：主推全部能力，文案不限定报告三件） */
export const EMPTY_STATE_COPY = {
  title: '开始与灵犀Agent对话',
  description:
    '灵犀Agent基于平台数据起草文档、对比结果、解读指标，也能生成用例、管理任务、诊断日志、校准设备——所有数值均来自平台数据，AI 只起草不算数。当前为 Demo 预览，Agent 能力接入后完整开放。',
  /** §3.3 区一「常用入门」（报告高频四卡，Report First 口径） */
  commonStartersTitle: '常用入门',
  /** §3.3 区二「全能力分组」（11 域入口卡） */
  capabilityGroupsTitle: '全能力分组',
  /** §3.3 无码域/无权限分组卡「待接入」徽标（可显不可执行，红线：不假接线） */
  capabilityPendingBadge: '待接入',
  placeholder: '描述你的报告需求，例如：帮我把任务 #320 的测试结果生成一份报告',
  loading: '正在加载对话...',
} as const

/** Demo 标注文案（§3.10；顶部条/全局浮窗头行 + §3.1B 本页能力条） */
export const DEMO_COPY = {
  badge: 'Demo',
  tooltip: '演示版：Agent 能力待接入，对话使用你配置的 LLM 供应商',
  floatingTooltip: '演示版，未接入实际后端',
  /** 全局浮窗「本页 Agent 能力」条（2026-10-17 负责人口径：每页 agent 可做的事不同） */
  pageCapabilityTitle: '本页 Agent 能力',
  pageCapabilityBadge: 'Demo 待接入',
  pageCapabilityTooltip:
    '演示版：此处仅展示本页 Agent 可做的事与快捷指令，能力接入后开放执行',
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
