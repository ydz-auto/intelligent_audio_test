/**
 * 首页域模型（照 api_gateway/schemas/home.py HomeStatsDetails 实测形态，
 * 03_首页.md §7：DTO snake_case 直通，接线时字段不返工）。
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
  with_endpoints: number
  endpoints: number
}

export type AudioFilesStats = {
  total: number
  dry: number
  noise: number
  prompt: number
}

export type HomeStatsDetails = {
  test_cases: TestCasesStats
  tasks: TasksStats
  devices: DevicesStats
  audio_files: AudioFilesStats
  playback_devices: number
  apis: ApisStats
  reports: number
  dimensions: DimensionsStats
  updated_at: string | null
}
