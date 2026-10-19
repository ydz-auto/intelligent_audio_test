/**
 * 首页/工作台统计域模型（domain 层，camelCase 域契约）。
 * 数据源：GET /api/v1/home/stats/details + GET /api/v1/home/stats/summary
 * （api_gateway/schemas/home.py 实测形态；snake_case→camelCase 转换收敛于
 * infrastructure/adapters/dto/home-adapter，domain 层不留 snake_case 穿透，
 * 04_控制台.md §2.0 数据命名口径）。
 */

export type TestCasesStats = {
  total: number
  groups: number
}

export type TasksStats = {
  total: number
  completed: number
  running: number
  failed: number
}

export type DevicesStats = {
  online: number
  offline: number
  total: number
}

export type ApisStats = {
  online: number
  offline: number
  total: number
}

export type DimensionsStats = {
  total: number
  withEndpoints: number
  endpoints: number
}

export type AudioFilesStats = {
  total: number
  dry: number
  noise: number
  prompt: number
}

/** GET /api/v1/home/stats/details（home.py HomeStatsDetails） */
export type HomeStatsDetails = {
  testCases: TestCasesStats
  tasks: TasksStats
  devices: DevicesStats
  audioFiles: AudioFilesStats
  playbackDevices: number
  apis: ApisStats
  reports: number
  dimensions: DimensionsStats
  updatedAt: string | null
}

/** home.py HomeStatsSummary.device_status：在线/离线计数（details 侧为含 total 的 DevicesStats） */
export interface DeviceStatus {
  online: number
  offline: number
}

export interface RecentTaskItem {
  id: number
  name: string
  /** 用例级被测设备类型集合（INT-79 读模型口径） */
  deviceTypes: string[]
  /** 任务状态枚举原值（pending/queued/running/…/reevaluate_queued） */
  status: string
  algorithmType: string | null
  totalCases: number
  completedCases: number
  createdAt: string | null
}

export interface TopGroupItem {
  id: string
  name: string
  caseCount: number
}

/** GET /api/v1/home/stats/summary（home.py HomeStatsSummary） */
export interface HomeStatsSummary {
  recentTasks: RecentTaskItem[]
  topGroups: TopGroupItem[]
  deviceStatus: DeviceStatus
}
