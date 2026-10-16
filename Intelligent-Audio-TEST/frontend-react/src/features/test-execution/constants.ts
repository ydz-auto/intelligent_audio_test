/**
 * 测试执行流程常量（interfaces/features/test-execution 层；10_测试执行.md §10）。
 * TEST_FLOW_CONFIG：testType 分叉声明式常量（步骤定义/文案/校验规则），
 * 照 setup-wizard STEPS / playground-parameter-controls 形态。
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
  /** 步骤名（E2E/API 分叉） */
  steps: FlowStepDefinition[]
  /** 测试类型锁（步骤二类型 facet 只读徽章） */
  lockedTypeBadge: '端到端测试' | 'API测试'
  /** 步骤三资源名词（设备/API） */
  resourceNoun: '设备' | 'API'
  /** 底部上下文提示（voice_llm 建议等） */
  voiceLlmAlert: string
  /** voice_llm 建议并发数 */
  voiceLlmConcurrency: number
}

export const TEST_FLOW_CONFIG: Record<'e2e' | 'api', TestFlowConfig> = {
  e2e: {
    title: '端到端测试',
    subtitle: '通过完整的测试流程验证语音产品的功能和性能',
    steps: [
      { index: 0, title: '选择算法', description: '选择本次测试使用的算法' },
      { index: 1, title: '选择测试用例', description: '勾选要执行的用例集' },
      { index: 2, title: '选择测试设备', description: '选择在线设备与执行参数' },
      { index: 3, title: '执行测试', description: '监控执行进度与结果' },
      { index: 4, title: '查看结果', description: '查看与导出测试报告' },
    ],
    lockedTypeBadge: '端到端测试',
    resourceNoun: '设备',
    voiceLlmAlert:
      'voice_llm 测试可能需要设备支持：音量控制、导轨控制、打断检测。请确认设备能力后再选择。',
    voiceLlmConcurrency: 2,
  },
  api: {
    title: 'API 测试',
    subtitle: '测试语音服务 API 的功能和性能，验证接口响应和数据正确性',
    steps: [
      { index: 0, title: '选择算法', description: '选择本次测试使用的算法' },
      { index: 1, title: '选择测试用例', description: '勾选要执行的用例集' },
      { index: 2, title: '选择被测 API', description: '选择在线 API 与执行参数' },
      { index: 3, title: '执行测试', description: '监控执行进度与结果' },
      { index: 4, title: '查看结果', description: '查看与导出测试报告' },
    ],
    lockedTypeBadge: 'API测试',
    resourceNoun: 'API',
    voiceLlmAlert:
      'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频',
    voiceLlmConcurrency: 2,
  },
}

/** 网络环境选项（E2E 执行参数，对齐端到端测试功能设计文档 :338） */
export const NETWORK_OPTIONS = ['默认', 'Wi-Fi', '移动网络', '飞行模式'] as const

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
