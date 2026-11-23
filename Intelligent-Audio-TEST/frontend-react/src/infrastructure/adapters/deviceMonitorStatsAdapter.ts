/**
 * 设备监控统计 DTO→Domain 适配器（infrastructure/adapters 层；契约 §1.2）。
 * snake_case → camelCase 唯一转换点；日期在此格式化为 MM-DD 供 vChart 使用，
 * 指标 null 原样保留（契约：无采点是断点，不得补 0 / 补均值）。
 */
import type {
  DeviceMonitorStats,
  DeviceStatsPoint,
} from '@/domain/models/deviceMonitorStats'
import type {
  DeviceMonitorStatsDto,
  DeviceMonitorStatsPointDto,
} from '@/infrastructure/dto/device-monitor-stats.dto'

/** ISO 日期 YYYY-MM-DD → MM-DD（非法形态原样保留，避免静默吞掉后端口径变化） */
export function formatStatsDate(iso: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(5, 10) : iso
}

function nullableNumber(value: number | null | undefined): number | null {
  return value == null ? null : value
}

export function statsPointFromDto(dto: DeviceMonitorStatsPointDto): DeviceStatsPoint {
  return {
    date: formatStatsDate(dto.date),
    isoDate: dto.date,
    availability: nullableNumber(dto.availability),
    cpu: nullableNumber(dto.cpu),
    memory: nullableNumber(dto.memory),
    battery: nullableNumber(dto.battery),
    errors: dto.errors ?? 0,
    operations: dto.operations ?? 0,
    healthCheckSamples: dto.health_check_samples ?? 0,
  }
}

export function deviceMonitorStatsFromDto(dto: DeviceMonitorStatsDto): DeviceMonitorStats {
  return {
    granularity: dto.granularity ?? 'day',
    startDate: dto.start_date,
    endDate: dto.end_date,
    deviceCount: dto.device_count ?? 0,
    points: (dto.points ?? []).map(statsPointFromDto),
  }
}
