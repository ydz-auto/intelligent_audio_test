/**
 * 首页统计领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/home.py::HomeStatsDetails / HomeStatsSummary
 *
 * 后端序列化输出为 snake_case，Infrastructure 层 statsAdapter 负责字段名转换。
 */

// ===== 统计详情（GET /home/stats/details） =====

/** 用例统计（对应后端 TestCasesStats） */
export interface TestCasesStats {
  total: number
  groups: number
}

/** 任务统计（对应后端 TasksStats） */
export interface TasksStats {
  total: number
  completed: number
  running: number
  failed: number
}

/** 设备统计（对应后端 DevicesStats） */
export interface DevicesStats {
  online: number
  offline: number
  total: number
}

/** 音频时长统计（对应后端 AudioDurationStats） */
export interface AudioDurationStats {
  total: number
  dry: number
  noise: number
  prompt: number
}

/** 音频文件统计（对应后端 AudioFilesStats） */
export interface AudioFilesStats {
  total: number
  dry: number
  noise: number
  prompt: number
  duration: AudioDurationStats
}

/** 被测 API 统计（对应后端 ApisStats） */
export interface ApisStats {
  online: number
  offline: number
  total: number
}

/** 评估维度统计（对应后端 DimensionsStats） */
export interface DimensionsStats {
  total: number
  withEndpoints: number
  endpoints: number
}

/** 首页统计详情（对应后端 HomeStatsDetails） */
export interface HomeStatsDetails {
  testCases: TestCasesStats
  tasks: TasksStats
  devices: DevicesStats
  audioFiles: AudioFilesStats
  playbackDevices: number
  apis: ApisStats
  reports: number
  dimensions: DimensionsStats
  updatedAt?: string
}

// ===== 统计摘要（GET /home/stats/summary） =====

/** 最近任务摘要（对应后端 RecentTaskItem） */
export interface RecentTaskSummary {
  id: number
  name: string
  type: string
  status: string
  algorithmType?: string
  totalCases: number
  completedCases: number
  createdAt?: string
}

/** 分组用例排行（对应后端 TopGroupItem） */
export interface TopGroupSummary {
  id: string
  name: string
  caseCount: number
}

/** 设备在线状态（对应后端 DeviceStatus） */
export interface DeviceStatusSummary {
  online: number
  offline: number
}

/** 首页统计摘要（对应后端 HomeStatsSummary） */
export interface HomeStatsSummary {
  recentTasks: RecentTaskSummary[]
  topGroups: TopGroupSummary[]
  deviceStatus: DeviceStatusSummary
}

// ===== 通用展示统计 =====

/** 通用统计项（图表/卡片展示用） */
export interface StatItem {
  label: string
  value: number | string
}
