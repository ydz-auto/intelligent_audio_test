/**
 * 首页/工作台统计 DTO（infrastructure/dto 层，raw snake_case 与后端契约一致）。
 * 对照 api_gateway/schemas/home.py：HomeStatsDetails / HomeStatsSummary；
 * 转换收敛于 adapters/dto/home-adapter（snake_case→camelCase 域模型）。
 */

export interface TestCasesStatsDto {
  total?: number
  groups?: number
}

export interface TasksStatsDto {
  total?: number
  completed?: number
  running?: number
  failed?: number
}

export interface DevicesStatsDto {
  online?: number
  offline?: number
  total?: number
}

export interface ApisStatsDto {
  online?: number
  offline?: number
  total?: number
}

export interface DimensionsStatsDto {
  total?: number
  with_endpoints?: number
  endpoints?: number
}

export interface AudioFilesStatsDto {
  total?: number
  dry?: number
  noise?: number
  prompt?: number
  /** 时长统计（后端 AudioDurationStats；前端概览不消费，仅 DTO 兼容） */
  duration?: { total: number; dry: number; noise: number; prompt: number }
}

export interface HomeStatsDetailsDto {
  test_cases?: TestCasesStatsDto
  tasks?: TasksStatsDto
  devices?: DevicesStatsDto
  audio_files?: AudioFilesStatsDto
  playback_devices?: number
  apis?: ApisStatsDto
  reports?: number
  dimensions?: DimensionsStatsDto
  updated_at?: string | null
}

export interface DeviceStatusDto {
  online?: number
  offline?: number
}

export interface RecentTaskItemDto {
  id: number
  name: string
  device_types?: string[]
  status: string
  /** 后端部分任务未返回该字段（Pydantic 排除 None）→ 兜底 null */
  algorithm_type?: string | null
  total_cases?: number
  completed_cases?: number
  created_at?: string | null
}

export interface TopGroupItemDto {
  id: string
  name: string
  case_count?: number
}

export interface HomeStatsSummaryDto {
  recent_tasks?: RecentTaskItemDto[]
  top_groups?: TopGroupItemDto[]
  device_status?: DeviceStatusDto
}
