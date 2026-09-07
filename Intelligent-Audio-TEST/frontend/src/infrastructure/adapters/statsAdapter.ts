/**
 * Stats Adapter —— HomeStatsDto(snake_case) → 首页统计 Domain(camelCase)
 *
 * ReadModel 定义在 domain/model/stats.ts（本任务新增），
 * 消费方 Home.vue 由 W2 迁移到新契约。
 */
import type {
  HomeStatsDetails,
  HomeStatsSummary,
  RecentTaskSummary,
  TopGroupSummary,
  DeviceStatusSummary,
  TestCasesStats,
  TasksStats,
  DevicesStats,
  AudioFilesStats,
  ApisStats,
  DimensionsStats,
} from '../../domain/model/stats'
import type {
  HomeStatsDetailsDto,
  HomeStatsSummaryDto,
  RecentTaskItemDto,
  TopGroupItemDto,
  DeviceStatusDto,
  TestCasesStatsDto,
  TasksStatsDto,
  DevicesStatsDto,
  AudioFilesStatsDto,
  ApisStatsDto,
  DimensionsStatsDto,
} from '../dto/statsDto'
import { toSafeNumber as num } from './commonAdapter'

function toTestCasesStats(dto: TestCasesStatsDto | undefined | null): TestCasesStats {
  return {
    total: num(dto?.total),
    groups: num(dto?.groups),
  }
}

function toTasksStats(dto: TasksStatsDto | undefined | null): TasksStats {
  return {
    total: num(dto?.total),
    completed: num(dto?.completed),
    running: num(dto?.running),
    failed: num(dto?.failed),
  }
}

function toDevicesStats(dto: DevicesStatsDto | undefined | null): DevicesStats {
  return {
    online: num(dto?.online),
    offline: num(dto?.offline),
    total: num(dto?.total),
  }
}

function toAudioFilesStats(dto: AudioFilesStatsDto | undefined | null): AudioFilesStats {
  return {
    total: num(dto?.total),
    dry: num(dto?.dry),
    noise: num(dto?.noise),
    prompt: num(dto?.prompt),
    duration: {
      total: num(dto?.duration?.total),
      dry: num(dto?.duration?.dry),
      noise: num(dto?.duration?.noise),
      prompt: num(dto?.duration?.prompt),
    },
  }
}

function toApisStats(dto: ApisStatsDto | undefined | null): ApisStats {
  return {
    online: num(dto?.online),
    offline: num(dto?.offline),
    total: num(dto?.total),
  }
}

function toDimensionsStats(dto: DimensionsStatsDto | undefined | null): DimensionsStats {
  return {
    total: num(dto?.total),
    withEndpoints: num(dto?.with_endpoints),
    endpoints: num(dto?.endpoints),
  }
}

// ===== DTO → Domain =====

/** 首页统计详情：HomeStatsDetailsDto → HomeStatsDetails */
export function toHomeStatsDetails(dto: HomeStatsDetailsDto | null | undefined): HomeStatsDetails {
  return {
    testCases: toTestCasesStats(dto?.test_cases),
    tasks: toTasksStats(dto?.tasks),
    devices: toDevicesStats(dto?.devices),
    audioFiles: toAudioFilesStats(dto?.audio_files),
    playbackDevices: num(dto?.playback_devices),
    apis: toApisStats(dto?.apis),
    reports: num(dto?.reports),
    dimensions: toDimensionsStats(dto?.dimensions),
    updatedAt: dto?.updated_at ?? undefined,
  }
}

function toRecentTask(dto: RecentTaskItemDto): RecentTaskSummary {
  return {
    id: dto.id,
    name: dto.name,
    type: dto.type,
    status: dto.status,
    algorithmType: dto.algorithm_type ?? undefined,
    totalCases: num(dto.total_cases),
    completedCases: num(dto.completed_cases),
    createdAt: dto.created_at ?? undefined,
  }
}

function toTopGroup(dto: TopGroupItemDto): TopGroupSummary {
  return {
    id: dto.id,
    name: dto.name,
    caseCount: num(dto.case_count),
  }
}

function toDeviceStatus(dto: DeviceStatusDto | undefined | null): DeviceStatusSummary {
  return {
    online: num(dto?.online),
    offline: num(dto?.offline),
  }
}

/** 首页统计摘要：HomeStatsSummaryDto → HomeStatsSummary */
export function toHomeStatsSummary(dto: HomeStatsSummaryDto | null | undefined): HomeStatsSummary {
  return {
    recentTasks: (dto?.recent_tasks ?? []).map(toRecentTask),
    topGroups: (dto?.top_groups ?? []).map(toTopGroup),
    deviceStatus: toDeviceStatus(dto?.device_status),
  }
}
