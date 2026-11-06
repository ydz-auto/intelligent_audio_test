/**
 * 首页/工作台统计 DTO→Domain 适配器（infrastructure/adapters/dto 层）。
 * 消费 dto/ 原始 snake_case，产出 camelCase 域模型（04_控制台.md §2.0 数据命名口径）；
 * 空/缺字段一律收敛 0/null，保证「无 undefined/NaN」。
 */
import type {
  HomeStatsDetails,
  HomeStatsSummary,
  RecentTaskItem,
  TopGroupItem,
} from '@/domain/models/home'
import type {
  HomeStatsDetailsDto,
  HomeStatsSummaryDto,
  RecentTaskItemDto,
  TopGroupItemDto,
} from '@/infrastructure/dto/home.dto'

function toRecentTaskItem(dto: RecentTaskItemDto): RecentTaskItem {
  return {
    id: dto.id,
    name: dto.name ?? '',
    deviceTypes: dto.device_types ?? [],
    status: dto.status ?? '',
    algorithmType: dto.algorithm_type ?? null,
    totalCases: dto.total_cases ?? 0,
    completedCases: dto.completed_cases ?? 0,
    createdAt: dto.created_at ?? null,
  }
}

function toTopGroupItem(dto: TopGroupItemDto): TopGroupItem {
  return {
    id: dto.id ?? '',
    name: dto.name ?? '',
    caseCount: dto.case_count ?? 0,
  }
}

export function toHomeStatsDetails(
  dto: HomeStatsDetailsDto | null | undefined
): HomeStatsDetails {
  return {
    testCases: {
      total: dto?.test_cases?.total ?? 0,
      groups: dto?.test_cases?.groups ?? 0,
    },
    tasks: {
      total: dto?.tasks?.total ?? 0,
      completed: dto?.tasks?.completed ?? 0,
      running: dto?.tasks?.running ?? 0,
      failed: dto?.tasks?.failed ?? 0,
    },
    devices: {
      online: dto?.devices?.online ?? 0,
      offline: dto?.devices?.offline ?? 0,
      total: dto?.devices?.total ?? 0,
    },
    audioFiles: {
      total: dto?.audio_files?.total ?? 0,
      dry: dto?.audio_files?.dry ?? 0,
      noise: dto?.audio_files?.noise ?? 0,
      prompt: dto?.audio_files?.prompt ?? 0,
    },
    playbackDevices: dto?.playback_devices ?? 0,
    apis: {
      online: dto?.apis?.online ?? 0,
      offline: dto?.apis?.offline ?? 0,
      total: dto?.apis?.total ?? 0,
    },
    reports: dto?.reports ?? 0,
    dimensions: {
      total: dto?.dimensions?.total ?? 0,
      withEndpoints: dto?.dimensions?.with_endpoints ?? 0,
      endpoints: dto?.dimensions?.endpoints ?? 0,
    },
    updatedAt: dto?.updated_at ?? null,
  }
}

export function toHomeStatsSummary(
  dto: HomeStatsSummaryDto | null | undefined
): HomeStatsSummary {
  return {
    recentTasks: (dto?.recent_tasks ?? []).map(toRecentTaskItem),
    topGroups: (dto?.top_groups ?? []).map(toTopGroupItem),
    deviceStatus: {
      online: dto?.device_status?.online ?? 0,
      offline: dto?.device_status?.offline ?? 0,
    },
  }
}
