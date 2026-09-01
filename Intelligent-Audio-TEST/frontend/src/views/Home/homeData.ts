import type { RouteLocationRaw } from 'vue-router'
import { TestType } from '@/shared/types/enums'

export interface StatItem {
  to: RouteLocationRaw
  icon: string
  numberKey: keyof typeof defaultAnimated
  label: string
  subKey: keyof typeof defaultAnimated
  subLabel: (val: number) => string
}

const defaultAnimated = {
  testCasesTotal: 0,
  testCasesGroups: 0,
  tasksTotal: 0,
  tasksCompleted: 0,
  devicesOnline: 0,
  devicesOffline: 0,
  audioFilesTotal: 0,
  audioFilesDry: 0,
  audioFilesDuration: 0,
  apisOnline: 0,
  apisTotal: 0,
  dimensionsTotal: 0,
  dimensionsEndpoints: 0
}

export const statCards: StatItem[] = [
  {
    to: '/TestCaseManager',
    icon: 'fas fa-clipboard-list',
    numberKey: 'testCasesTotal',
    label: '测试用例',
    subKey: 'testCasesGroups',
    subLabel: (v) => `${v} 个分组`
  },
  {
    to: '/Tasks',
    icon: 'fas fa-tasks',
    numberKey: 'tasksTotal',
    label: '测试任务',
    subKey: 'tasksCompleted',
    subLabel: (v) => `${v} 已完成`
  },
  {
    to: '/Evaluation',
    icon: 'fas fa-star',
    numberKey: 'dimensionsTotal',
    label: '评估维度',
    subKey: 'dimensionsEndpoints',
    subLabel: (v) => `${v} 个端点`
  },
  {
    to: '/AudioImport',
    icon: 'fas fa-music',
    numberKey: 'audioFilesTotal',
    label: '音频文件',
    subKey: 'audioFilesDry',
    subLabel: (v) => `${v} 个干音`
  },
  {
    to: '/Device',
    icon: 'fas fa-headphones',
    numberKey: 'devicesOnline',
    label: '在线设备',
    subKey: 'devicesOffline',
    subLabel: (v) => `${v} 离线`
  },
  {
    to: '/APITest',
    icon: 'fas fa-server',
    numberKey: 'apisTotal',
    label: 'API服务',
    subKey: 'apisOnline',
    subLabel: (v) => `${v} 在线`
  }
]

export interface WorkflowStep {
  label: string
  desc: string
}

export const workflowSteps: WorkflowStep[] = [
  { label: '选择算法', desc: '配置测试算法参数' },
  { label: '选择用例', desc: '创建或选择测试用例' },
  { label: '选择设备', desc: '配置测试设备参数' },
  { label: '执行测试', desc: '运行语音测试流程' },
  { label: '查看结果', desc: '分析测试评估报告' }
]

export interface TestTypeCard {
  to: RouteLocationRaw
  icon: string
  title: string
  description: string
  list: string[]
  variant: (typeof TestType)[keyof typeof TestType]
}

export const testTypeCards: TestTypeCard[] = [
  {
    to: '/E2ETest',
    icon: 'fas fa-project-diagram',
    title: '端到端测试',
    description:
      '在真实设备上执行端到端语音测试，支持多设备并行测试，实时监控测试进度和结果。',
    list: ['多设备并行测试', '实时进度监控', '自动化测试流程'],
    variant: TestType.E2E
  },
  {
    to: '/APITest',
    icon: 'fas fa-exchange-alt',
    title: 'API测试',
    description:
      '测试语音识别和翻译API等的性能和准确率，支持批量测试和结果对比分析。',
    list: ['API性能测试', '批量测试执行', '结果对比分析'],
    variant: TestType.API
  }
]

export interface DetailSideCard {
  icon: string
  title: string
  desc: string
}

export interface DetailSection {
  title: string
  subtitle: string
  variant: string
  iconLarge: string
  mainTitle: string
  mainDescription: string
  features: { icon: string; text: string }[]
  sideCards: DetailSideCard[]
  ctaTo: RouteLocationRaw
  ctaVariant: string
  ctaText: string
  reverse: boolean
  altBg: boolean
}

export const detailSections: DetailSection[] = [
  {
    title: '端到端测试系统',
    subtitle: '在真实设备上执行完整的语音测试流程，模拟真实用户使用场景',
    variant: '',
    iconLarge: 'fas fa-mobile-alt',
    mainTitle: '真实设备测试',
    mainDescription:
      '在真实Android/鸿蒙设备上执行端到端语音测试，模拟真实用户使用场景。支持多设备并行测试，同时在多台设备上运行相同的测试用例，快速对比不同设备的表现差异。',
    features: [
      { icon: 'fas fa-layer-group', text: '多设备并行测试' },
      { icon: 'fas fa-tachometer-alt', text: '实时进度监控' },
      { icon: 'fas fa-history', text: '完整执行记录' }
    ],
    sideCards: [
      { icon: 'fas fa-list-ol', title: '五步测试流程', desc: '选择算法 → 选择用例 → 选择设备 → 执行测试 → 查看报告' },
      { icon: 'fas fa-tags', title: '用例分类管理', desc: '唤醒词、命令识别、语音识别、多轮对话测试' },
      { icon: 'fas fa-chart-bar', title: '可视化报告', desc: '准确率对比、正态分布、趋势分析图表' },
      { icon: 'fas fa-exclamation-triangle', title: '异常处理', desc: '支持重试和跳过失败用例' }
    ],
    ctaTo: '/E2ETest',
    ctaVariant: 'e2e',
    ctaText: '立即体验',
    reverse: false,
    altBg: false
  },
  {
    title: 'API测试系统',
    subtitle: '测试语音识别和翻译API的性能与准确率，支持批量测试和结果对比',
    variant: 'api',
    iconLarge: 'fas fa-exchange-alt',
    mainTitle: 'API性能测试',
    mainDescription:
      '测试第三方语音识别和翻译API的性能和准确率。支持批量测试执行，自动记录响应时间、并发数和成功率。提供详细的结果对比分析，帮助优化API使用策略。',
    features: [
      { icon: 'fas fa-bolt', text: '性能基准测试' },
      { icon: 'fas fa-balance-scale', text: '结果对比分析' },
      { icon: 'fas fa-heartbeat', text: '健康状态监控' }
    ],
    sideCards: [
      { icon: 'fas fa-server', title: '多API支持', desc: '支持对接多个语音识别和翻译服务' },
      { icon: 'fas fa-users', title: '并发控制', desc: '自定义并发数和请求间隔' },
      { icon: 'fas fa-stopwatch', title: '响应时间分析', desc: '实时统计平均响应时间和超时率' },
      { icon: 'fas fa-file-export', title: '报告导出', desc: '支持CSV和PDF格式导出' }
    ],
    ctaTo: '/APITest',
    ctaVariant: 'api',
    ctaText: '立即体验',
    reverse: true,
    altBg: true
  },
  {
    title: '音频导入功能',
    subtitle: '多种音频导入方式，支持批量操作和自动生成测试用例',
    variant: 'audio',
    iconLarge: 'fas fa-music',
    mainTitle: '灵活音频管理',
    mainDescription:
      '支持多种音频导入方式，包括本地上传、文件夹批量导入。导入时可选择自动生成测试用例，支持设置测试类型、播放设备和声压级。提供音频预览、格式转换和元数据编辑功能。',
    features: [
      { icon: 'fas fa-cloud-upload-alt', text: '多途径导入' },
      { icon: 'fas fa-magic', text: '自动生成用例' },
      { icon: 'fas fa-sliders-h', text: '声压级配置' }
    ],
    sideCards: [
      { icon: 'fas fa-file-audio', title: '多格式支持', desc: 'MP3、WAV、FLAC、AAC等常见格式' },
      { icon: 'fas fa-filter', title: '智能筛选', desc: '按格式、采样率、标签、时长筛选' },
      { icon: 'fas fa-wave-square', title: '格式转换', desc: '支持采样率和声道转换' },
      { icon: 'fas fa-info-circle', title: '元数据管理', desc: '编辑ASR文本、标签、分类信息' }
    ],
    ctaTo: '/AudioImport',
    ctaVariant: 'audio',
    ctaText: '立即体验',
    reverse: false,
    altBg: false
  },
  {
    title: '用例管理',
    subtitle: '统一管理端到端测试用例和API测试用例，支持分类、标签和批量操作',
    variant: 'cases',
    iconLarge: 'fas fa-tasks',
    mainTitle: '用例集中管理',
    mainDescription:
      '统一管理端到端测试用例和API测试用例，支持按测试类型分组管理。提供用例标签系统，方便分类和筛选。支持批量导入导出、复制和移动操作，提高用例管理效率。',
    features: [
      { icon: 'fas fa-folder', text: '分类管理' },
      { icon: 'fas fa-tags', text: '标签系统' },
      { icon: 'fas fa-copy', text: '批量操作' }
    ],
    sideCards: [
      { icon: 'fas fa-list', title: '用例类型', desc: '唤醒词、命令识别、语音识别、多轮对话' },
      { icon: 'fas fa-file-import', title: '批量导入', desc: '支持从文件和文件夹批量导入' },
      { icon: 'fas fa-file-export', title: '导出功能', desc: '支持导出为Excel格式' },
      { icon: 'fas fa-search', title: '快速搜索', desc: '支持关键词和标签筛选' }
    ],
    ctaTo: '/TestCaseManager',
    ctaVariant: 'cases',
    ctaText: '立即体验',
    reverse: true,
    altBg: true
  },
  {
    title: '任务管理',
    subtitle: '查看和管理测试任务执行记录，支持历史查询、结果回溯和任务合并',
    variant: 'tasks',
    iconLarge: 'fas fa-history',
    mainTitle: '任务历史追踪',
    mainDescription:
      '查看和管理所有测试任务的执行记录，支持按时间、状态、类型筛选。提供任务详情查看，包括执行进度、结果统计和关联信息。支持历史任务结果回溯、报告重新生成，以及多任务合并对比分析。',
    features: [
      { icon: 'fas fa-filter', text: '多维筛选' },
      { icon: 'fas fa-chart-pie', text: '结果统计' },
      { icon: 'fas fa-object-group', text: '任务合并' }
    ],
    sideCards: [
      { icon: 'fas fa-clock', title: '时间筛选', desc: '按日期范围快速筛选任务' },
      { icon: 'fas fa-check-circle', title: '状态筛选', desc: '全部、成功、失败、进行中' },
      { icon: 'fas fa-copy', title: '任务合并', desc: '多任务结果合并与对比分析' },
      { icon: 'fas fa-redo', title: '结果回溯', desc: '查看历史报告和详细结果' }
    ],
    ctaTo: '/Tasks',
    ctaVariant: 'tasks',
    ctaText: '立即体验',
    reverse: false,
    altBg: false
  },
  {
    title: '报告管理',
    subtitle: '多维度测试报告查看、对比分析和导出功能',
    variant: 'reports',
    iconLarge: 'fas fa-chart-pie',
    mainTitle: '全方位报告分析',
    mainDescription:
      '提供完整的测试报告管理功能，支持多维度数据查看和对比分析。可按任务、时间、类型筛选历史报告，支持单任务详细报告和跨任务对比报告。报告数据支持多种图表展示和格式导出。',
    features: [
      { icon: 'fas fa-file-alt', text: '详细报告查看' },
      { icon: 'fas fa-balance-scale', text: '跨任务对比' },
      { icon: 'fas fa-file-export', text: '多格式导出' }
    ],
    sideCards: [
      { icon: 'fas fa-history', title: '历史报告', desc: '按时间、任务类型筛选历史测试报告' },
      { icon: 'fas fa-chart-bar', title: '数据可视化', desc: '准确率曲线、正态分布、对比图表' },
      { icon: 'fas fa-columns', title: '对比分析', desc: '多任务、多维度结果对比展示' }
    ],
    ctaTo: '/history-reports',
    ctaVariant: 'reports',
    ctaText: '查看报告',
    reverse: false,
    altBg: false
  },
  {
    title: '评估系统',
    subtitle: '多维度语音评估，支持自定义评估规则和API集成',
    variant: 'evaluation',
    iconLarge: 'fas fa-star',
    mainTitle: '智能评估引擎',
    mainDescription:
      '提供多维度语音质量评估，包括准确率、召回率、F1分数等核心指标。支持自定义评估规则和第三方评估API集成，满足不同场景的评估需求。实时计算评估分数，快速定位语音识别问题。',
    features: [
      { icon: 'fas fa-calculator', text: '多指标计算' },
      { icon: 'fas fa-cogs', text: '自定义规则' },
      { icon: 'fas fa-plug', text: 'API扩展' }
    ],
    sideCards: [
      { icon: 'fas fa-check-circle', title: 'ASR准确率', desc: '字错率、词错率、句错率等评估' },
      { icon: 'fas fa-language', title: '翻译质量', desc: 'COMET 等评分支持' },
      { icon: 'fas fa-balance-scale', title: '准确率与召回', desc: 'Precision、Recall、F1 分数' },
      { icon: 'fas fa-wind', title: '流畅度评估', desc: '气泡率、停顿率分析' }
    ],
    ctaTo: '/Evaluation',
    ctaVariant: 'evaluation',
    ctaText: '立即体验',
    reverse: true,
    altBg: true
  },
  {
    title: '设备管理',
    subtitle: '统一管理测试设备和播放设备，支持状态监控和分组配置',
    variant: 'device',
    iconLarge: 'fas fa-mobile-alt',
    mainTitle: '设备集中管理',
    mainDescription:
      '支持管理Android/鸿蒙真机设备和播放设备。实时监控设备在线状态，自动检测设备连接情况。支持设备分组管理，方便批量选择和测试执行。',
    features: [
      { icon: 'fas fa-wifi', text: '状态监控' },
      { icon: 'fas fa-layer-group', text: '设备分组' },
      { icon: 'fas fa-headphones', text: '播放配置' }
    ],
    sideCards: [
      { icon: 'fab fa-android', title: 'Android设备', desc: 'ADB连接，自动识别设备信息' },
      { icon: 'fab fa-apple', title: '鸿蒙设备', desc: 'HDC连接，自动识别设备信息' },
      { icon: 'fas fa-volume-up', title: '播放设备', desc: '声卡通道选择，采样率配置' },
      { icon: 'fas fa-info-circle', title: '设备信息', desc: '系统版本、APP版本自动获取' }
    ],
    ctaTo: '/Device',
    ctaVariant: 'device',
    ctaText: '立即体验',
    reverse: false,
    altBg: false
  },
  {
    title: '声压级映射',
    subtitle: '精确配置音频增益与声压级关系，确保测试环境一致性',
    variant: 'spl',
    iconLarge: 'fas fa-sliders-h',
    mainTitle: '声压级校准',
    mainDescription:
      '配置音频文件的数字增益与实际声压级的对应关系。支持多个声压级节点的线性插值，确保不同音量下的测试准确性。可导入校准数据，实现自动化声压级管理。',
    features: [
      { icon: 'fas fa-chart-line', text: '增益曲线配置' },
      { icon: 'fas fa-database', text: '校准数据导入' },
      { icon: 'fas fa-broadcast-tower', text: '实时声压计算' }
    ],
    sideCards: [
      { icon: 'fas fa-volume-up', title: '增益配置', desc: '数字增益到声压的精确映射' },
      { icon: 'fas fa-ruler-combined', title: '多节点校准', desc: '支持多个声压级节点插值' },
      { icon: 'fas fa-file-import', title: '数据导入', desc: '支持校准数据批量导入' },
      { icon: 'fas fa-calculator', title: '精度控制', desc: '小数位数和容差设置' }
    ],
    ctaTo: '/SPLMapping',
    ctaVariant: 'spl',
    ctaText: '立即体验',
    reverse: true,
    altBg: true
  },
  {
    title: '并发与异步',
    subtitle: '高效的任务调度机制，支持多任务并行处理',
    variant: 'async',
    iconLarge: 'fas fa-tachometer-alt',
    mainTitle: '高效任务调度',
    mainDescription:
      '基于异步IO的任务调度系统，支持多任务并行执行。智能负载均衡自动分配任务，避免资源争用。WebSocket实时推送测试进度，任务状态秒级更新。',
    features: [
      { icon: 'fas fa-bolt', text: '异步执行' },
      { icon: 'fas fa-balance-scale', text: '负载均衡' },
      { icon: 'fas fa-sync', text: '实时推送' }
    ],
    sideCards: [
      { icon: 'fas fa-rocket', title: '快速响应', desc: '异步IO设计，任务提交即返回' },
      { icon: 'fas fa-users-cog', title: '并发控制', desc: '可配置的最大并发数和队列长度' },
      { icon: 'fas fa-server', title: '资源隔离', desc: '单任务资源限制，防止系统过载' },
      { icon: 'fas fa-history', title: '断点续传', desc: '支持暂停、恢复和任务重试' }
    ],
    ctaTo: '/Tasks',
    ctaVariant: 'tasks',
    ctaText: '立即体验',
    reverse: false,
    altBg: false
  }
]

export interface FeatureCard {
  to: RouteLocationRaw
  icon: string
  title: string
  description: string
  list: string[]
  link: string
  variant: string
}

export const featureCards: FeatureCard[] = [
  {
    to: '/E2ETest',
    icon: 'fas fa-mobile-alt',
    title: '端到端测试',
    description: '在真实设备上执行端到端语音测试，支持多设备并行测试和实时进度监控。',
    list: ['多设备并行测试', '五步测试流程', '可视化报告'],
    link: '开始测试',
    variant: 'e2e'
  },
  {
    to: '/APITest',
    icon: 'fas fa-exchange-alt',
    title: 'API测试',
    description: '测试语音识别和翻译API的性能与准确率，支持批量测试和结果对比分析。',
    list: ['API性能测试', '并发控制', '健康状态监控'],
    link: '开始测试',
    variant: 'api'
  },
  {
    to: '/AudioImport',
    icon: 'fas fa-music',
    title: '音频管理',
    description: '统一管理测试所需的音频文件，支持批量导入、标签分类和音频预览，可导入音频自动生成测试用例。',
    list: ['批量音频导入', '导入生成用例', '音频预览播放'],
    link: '管理音频',
    variant: 'audio'
  },
  {
    to: '/TestCaseManager',
    icon: 'fas fa-tasks',
    title: '用例管理',
    description: '统一管理端到端测试用例和API测试用例，支持用例分类、标签管理和批量操作。',
    list: ['用例分类管理', '标签系统', '批量导入导出'],
    link: '管理用例',
    variant: 'cases'
  },
  {
    to: '/tasks',
    icon: 'fas fa-history',
    title: '任务记录',
    description: '查看和管理所有测试任务的执行记录，支持历史任务查询和结果回溯。',
    list: ['任务历史记录', '结果查询分析', '报告导出'],
    link: '查看任务',
    variant: 'tasks'
  },
  {
    to: '/Evaluation',
    icon: 'fas fa-star',
    title: '评估维度',
    description: '配置和管理语音测试的评估维度，支持多种评估指标和自定义评估规则。',
    list: ['多维度评估', '自定义指标', '评估API管理'],
    link: '配置维度',
    variant: 'evaluation'
  },
  {
    to: '/Device',
    icon: 'fas fa-mobile-alt',
    title: '设备管理',
    description: '管理测试设备和播放设备，支持设备状态监控和设备分组。',
    list: ['设备状态监控', '播放设备配置', '设备分组管理'],
    link: '管理设备',
    variant: 'device'
  },
  {
    to: '/SPLMapping',
    icon: 'fas fa-sliders-h',
    title: '声压级映射',
    description: '配置音频数字增益与实际声压的关系，确保测试环境的声压级准确性。',
    list: ['增益配置', '声压校准', '精度控制'],
    link: '配置映射',
    variant: 'spl'
  }
]

export const systemInfo = [
  { label: '系统版本', value: '1.0.0' },
  { label: '前端框架', value: 'Vue 3 + Electron' },
  { label: '后端框架', value: 'Flask + PostgreSql' },
  { label: 'Python版本', value: '3.12' }
]

export const helpLinks = [
  { to: '/Device', icon: 'fas fa-headphones', text: '配置播放设备' },
  { to: '/Evaluation', icon: 'fas fa-star', text: '配置评估维度' },
  { to: '/AudioImport', icon: 'fas fa-music', text: '导入测试音频' }
]

export type AnimatedStats = typeof defaultAnimated
