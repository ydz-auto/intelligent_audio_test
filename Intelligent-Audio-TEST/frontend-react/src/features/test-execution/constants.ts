/**
 * 测试执行流程常量（interfaces/features/test-execution 层；10_测试执行.md §10，
 * INT-486 合并口径：不再有「选择算法」步骤——算法切换已全局化（INT-436/442 概览大卡
 * + 导航栏切换器）；端到端+API 合并 /start-test 单入口。
 * INT-486 2026-10-16 追加口径（负责人定稿）：开始测试不再分 E2E/API 模式——单流程，
 * 第二步资源选择同屏同选设备 + API（混合执行），用例不分类型。
 * TEST_FLOW_CONFIG：单流程声明式常量（步骤定义/文案），照 setup-wizard STEPS 形态。
 */
import type { FlowStep } from '@/application/test-execution/useFlowSteps'

export interface FlowStepDefinition {
  index: FlowStep
  title: string
  description: string
}

export interface TestFlowConfig {
  /** 页面标题与副文 */
  title: string
  subtitle: string
  /** 步骤名（单流程，不分 E2E/API） */
  steps: FlowStepDefinition[]
  /** 底部上下文提示（voice_llm 建议等） */
  voiceLlmAlert: string
  /** voice_llm 建议并发数 */
  voiceLlmConcurrency: number
}

/** 算法类型码：语音大模型（GET /algorithm/options 的 value 口径；多轮/打断/拒识语义） */
export const VOICE_LLM_ALGORITHM_TYPE = 'voice_llm'

export const TEST_FLOW_CONFIG: TestFlowConfig = {
  title: '开始测试',
  subtitle: '选择用例与设备/API，在同一流程内完成语音测试与报告生成',
  steps: [
    { index: 0, title: '选择测试用例', description: '勾选要执行的用例集' },
    { index: 1, title: '选择设备/API', description: '同屏选择设备与 API（混合执行）' },
    { index: 2, title: '执行测试', description: '监控执行进度与结果' },
    { index: 3, title: '查看结果', description: '查看与导出测试报告' },
  ],
  voiceLlmAlert:
    'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频；物理设备测试可能需要音量控制、导轨控制、打断检测等设备能力。',
  voiceLlmConcurrency: 2,
}

/** 网络环境选项（执行参数，对齐端到端测试功能设计文档 :338） */
export const NETWORK_OPTIONS = ['默认', 'Wi-Fi', '移动网络', '飞行模式'] as const

/**
 * Select 选项（value/label 成对；直接作 base-ui Select 的 items，关闭态才能显示 label，
 * 见 INT-1633 / 日志域 INT-1561 同口径）
 */
export type ResourceSelectOption = { value: string; label: string }

/** 设备/API 状态筛选（§3.6 步骤二筛选行文案） */
export const RESOURCE_STATUS_OPTIONS: ResourceSelectOption[] = [
  { value: 'all', label: '全部状态' },
  { value: 'online', label: '在线' },
  { value: 'offline', label: '离线' },
]

/** 被测对象系统类型筛选（INT-486 口径 2026-10-16：Android/鸿蒙/播放设备等；数据来自 device.system/type） */
export const RESOURCE_SYSTEM_OPTIONS: ResourceSelectOption[] = [
  { value: 'all', label: '全部系统' },
  { value: 'android', label: 'Android' },
  { value: 'harmony', label: '鸿蒙' },
  { value: 'api', label: 'API 网关' },
]

/** 被测 API 厂商筛选（INT-486 口径 2026-10-16：按 API 筛选维度含厂商） */
export const RESOURCE_VENDOR_OPTIONS: ResourceSelectOption[] = [
  { value: 'all', label: '全部厂商' },
  { value: '内部 ASR 组', label: '内部 ASR 组' },
  { value: '内部唤醒组', label: '内部唤醒组' },
  { value: 'TTS 组', label: 'TTS 组' },
]

/** 被测 API 协议筛选（INT-486 口径；INT-1800：值域改为 B0 的 4 个规范值） */
export const RESOURCE_PROTOCOL_OPTIONS: ResourceSelectOption[] = [
  { value: 'all', label: '全部协议' },
  { value: 'http', label: 'HTTP' },
  { value: 'websocket', label: 'WebSocket' },
  { value: 'sse', label: 'SSE' },
  { value: 'grpc', label: 'gRPC' },
]

/** 被测 API 流式性筛选（INT-1800：第二维，与协议独立） */
export const RESOURCE_STREAMING_OPTIONS: ResourceSelectOption[] = [
  { value: 'all', label: '全部形态' },
  { value: 'streaming', label: '流式' },
  { value: 'non_streaming', label: '非流式' },
]

/**
 * 实验室-被测对象绑定 mock（INT-487 设备-实验室绑定待接线；本页演示过滤口径）。
 * 默认「全部实验室」不筛；选择实验室后设备/API 列表按 lab 成员过滤。
 */
export const MOCK_RESOURCE_LABS: {
  id: string
  name: string
  deviceIds: number[]
  apiIds: number[]
}[] = [
  { id: 'lab-a', name: '旗舰实验室', deviceIds: [1, 2, 4, 5], apiIds: [11, 12] },
  { id: 'lab-b', name: '车载实验室', deviceIds: [6], apiIds: [13] },
  { id: 'lab-c', name: '入门实验室', deviceIds: [3], apiIds: [12] },
]

/** 报告模板选项（对齐 15_报告域 §5 模板清单） */
export const REPORT_TEMPLATE_OPTIONS = [
  '标准模板',
  '详细指标模板',
  '精简汇报模板',
  '多算法对比模板',
] as const

/** 报告包含内容（默认全勾） */
export const REPORT_INCLUDE_OPTIONS = [
  { value: 'includeCharts', label: '图表' },
  { value: 'includeDetailedLogs', label: '详细日志' },
  { value: 'includeReferenceParams', label: '参考参数' },
] as const

/** 导出格式（15_报告域 §4.3；POST /reports/export format 枚举） */
export const EXPORT_FORMATS = [
  { value: 'csv', label: 'CSV' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
] as const
