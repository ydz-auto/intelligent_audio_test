/**
 * Stats（首页统计）DTO —— snake_case
 * 对应后端 api_gateway/schemas/home.py::HomeStatsDetails / HomeStatsSummary
 * 及其子结构（TestCasesStats / TasksStats / DevicesStats / AudioFilesStats /
 * ApisStats / DimensionsStats / RecentTaskItem / TopGroupItem / DeviceStatus）
 */

/** 对应后端 TestCasesStats */
export interface TestCasesStatsDto {
  total: number
  groups: number
}

/** 对应后端 TasksStats */
export interface TasksStatsDto {
  total: number
  completed: number
  running: number
  failed: number
}

/** 对应后端 DevicesStats */
export interface DevicesStatsDto {
  online: number
  offline: number
  total: number
}

/** 对应后端 AudioDurationStats */
export interface AudioDurationStatsDto {
  total: number
  dry: number
  noise: number
  prompt: number
}

/** 对应后端 AudioFilesStats */
export interface AudioFilesStatsDto {
  total: number
  dry: number
  noise: number
  prompt: number
  duration: AudioDurationStatsDto
}

/** 对应后端 ApisStats */
export interface ApisStatsDto {
  online: number
  offline: number
  total: number
}

/** 对应后端 DimensionsStats */
export interface DimensionsStatsDto {
  total: number
  with_endpoints: number
  endpoints: number
}

/** 对应后端 HomeStatsDetails */
export interface HomeStatsDetailsDto {
  test_cases: TestCasesStatsDto
  tasks: TasksStatsDto
  devices: DevicesStatsDto
  audio_files: AudioFilesStatsDto
  playback_devices: number
  apis: ApisStatsDto
  reports: number
  dimensions: DimensionsStatsDto
  updated_at?: string | null
}

/** 对应后端 RecentTaskItem */
export interface RecentTaskItemDto {
  id: number
  name: string
  type: string
  status: string
  algorithm_type?: string | null
  total_cases: number
  completed_cases: number
  created_at?: string | null
}

/** 对应后端 TopGroupItem */
export interface TopGroupItemDto {
  id: string
  name: string
  case_count: number
}

/** 对应后端 DeviceStatus */
export interface DeviceStatusDto {
  online: number
  offline: number
}

/** 对应后端 HomeStatsSummary */
export interface HomeStatsSummaryDto {
  recent_tasks: RecentTaskItemDto[]
  top_groups: TopGroupItemDto[]
  device_status: DeviceStatusDto
}
